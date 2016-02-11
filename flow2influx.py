#!/usr/bin/python

import MySQLdb as mdb
from influxdb import InfluxDBClient
from collections import defaultdict
from pprint import pprint
import rrdtool
import sys


rrdpath = '/some/path/rrd/'
sampling = '1000'

sql = {
  'host': '127.0.0.1',
  'db': 'pmacct',
  'user': 'pmacct',
  'passwd': 'XXXX',
}

idb = {
  'host': '10.3.0.20',
  'port': 8186,
  'db': 'flows',
  'user': 'flow',
  'passwd': 'XXXX',
}

custs_map = {
  'all': '000',
  'cust1': '100',
  'cust2': '101',
  'cust3': '102',
  'cust4': '103',
}

# autovivifaction
def tree():
    return defaultdict(tree)
metrics = defaultdict(tree)


# connect mysql
try:
    con = mdb.connect(sql['host'], sql['user'], sql['passwd'], sql['db'])
    cur = con.cursor()
except mdb.Error, e:
    print "Error %d: %s" % (e.args[0],e.args[1])
    sys.exit(1)


def sql_query(req):
    cur.execute(req)
    rows = cur.fetchall()
    return rows


# connect influxdb
try:
    idb = InfluxDBClient(idb['host'], idb['port'], idb['user'], idb['passwd'], idb['db'])
except:
    print "Error connecting influxdb"
    sys.exit(1)


def write_influxdb(measurement, tags, fields):
    json = [{ 'measurement': measurement, 'tags': tags, 'fields': fields }]
    try:
        print json
        idb.write_points(json)
    except:
        print 'influxdb update failed for ' + json


def write_rrd(cust, *argv):
    rrdfile = rrdpath+cust + "_flow/billing.rrd"
    try:
        print 'rrdtool update %s:%s:%s' % (rrdfile, argv[0], argv[1])
        rrdtool.update(rrdfile, 'N:%s:%s' % (argv[0], argv[1]))
    except:
        print 'update failed of ' + rrdfile


def get_ifstats(direc, cust, id_cust):
    req = "select iface_desc, router_desc, sum(bytes)*%s*8/60 as bits, sum(packets)*%s/60 as pkts " % (sampling, sampling)
    req += "from netflow_if_%s " % direc
    req += "left join interface_map on tag=iface_id "
    req += "where "
    if cust != 'all':
        req += "tag2=%s and " % id_cust
    req += "stamp_inserted = date_format(now() - interval 2 minute, '%Y-%m-%d %H:%i:00') "
    req += "group by tag"

    total_bps = 0.0
    total_pps = 0.0
    for row in sql_query(req):
        total_bps += float(row[2])
        total_pps += float(row[3])
        metrics["if_"+direc][(row[0],row[1],cust)]['bps'] = float(row[2])
        metrics["if_"+direc][(row[0],row[1],cust)]['pps'] = float(row[3])

    metrics["if_"+direc][('any','any',cust)]['bps'] = float(total_bps)
    metrics["if_"+direc][('any','any',cust)]['pps'] = float(total_pps)


def get_flowstats(direc, cust, id_cust):
    req = "select iface_desc, router_desc, count(netflow_%s_hour.id)*%s/60 as fps " % (direc, sampling)
    req += "from netflow_%s_hour " % direc
    req += "left join interface_map on tag=iface_id "
    req += "where "
    if cust != 'all':
        req += "tag2=%s and " % id_cust
    req += "stamp_inserted = date_format(now() - interval 2 minute, '%Y-%m-%d %H:%i:00') "
    req += "group by tag"

    total_fps = 0.0
    for row in sql_query(req):
        total_fps += float(row[2])
        metrics["if_"+direc][(row[0],row[1],cust)]['fps'] = float(row[2])

    metrics["if_"+direc][('any','any',cust)]['fps'] = float(total_fps)


def get_protostats(direc, cust, id_cust):
    req = "select ip_proto, sum(bytes)*%s*8/60 as bits " % sampling
    req += "from netflow_%s_hour " % direc
    req += "where "
    if cust != 'all':
        req += "tag2=%s and " % id_cust
    req += "stamp_inserted = date_format(now() - interval 2 minute, '%Y-%m-%d %H:%i:00') "
    req += "group by ip_proto"

    for row in sql_query(req):
        metrics["proto_"+direc][(row[0],cust)]['bps'] = float(row[1])


def get_bgpstats(direc, cust, id_cust):
    if direc == 'out':
        as_dir = 'as_dst'
    elif direc == 'in':
        as_dir = 'as_src'

    req = "select %s, sum(bytes)*%s*8/60 as bits, sum(packets)*%s/60 as pkts " % (as_dir, sampling, sampling)
    req += "from netflow_asn_%s " % direc
    req += "where stamp_inserted = date_format(now() - interval 2 minute, '%Y-%m-%d %H:%i:00') "
    req += "group by %s" % as_dir

    for row in sql_query(req):
        metrics["as_"+direc][(row[0],cust)]['bps'] = float(row[1])
        metrics["as_"+direc][(row[0],cust)]['pps'] = float(row[2])



## 1. get the data

# 1.1 get interface statistics
# loop over customer
for cust in custs_map:
    get_ifstats('in', cust, custs_map[cust])
    get_ifstats('out', cust, custs_map[cust])
    get_flowstats('in', cust, custs_map[cust])
    get_flowstats('out', cust, custs_map[cust])

# 1.2 get protocol statistics
get_protostats('in', 'all', '000')
get_protostats('out', 'all', '000')

# 1.3 get bgp statistics
get_bgpstats('in', 'all', '000')
get_bgpstats('out', 'all', '000')


## 2. write the data to influxdb

# 1.1 write interface statistics
for m in ['if_in', 'if_out']:
    for k,v in metrics[m].iteritems():
        write_influxdb(m, {'interface':k[0],'router':k[1],'customer':k[2]}, dict(v))

# 1.2 write protocol statistics
for m in ['proto_in', 'proto_out']:
    for k,v in metrics[m].iteritems():
        write_influxdb(m, {'type':k[0],'customer':k[1]}, dict(v))

# 1.3 write bgp statistics
for m in ['as_in', 'as_out']:
    for k,v in metrics[m].iteritems():
        write_influxdb(m, {'asn':k[0],'customer':k[1]}, dict(v))


## 3. write the data to rdd
for cust in custs_map:
    in_bps = metrics['if_in'][('any','any',cust)]['bps']
    out_bps = metrics['if_out'][('any','any',cust)]['bps']
    write_rrd(cust, int(in_bps/8), int(out_bps/8))


