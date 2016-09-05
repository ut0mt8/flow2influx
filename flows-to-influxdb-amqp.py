#!/usr/bin/env python
#
import sys
import pika
import json
import time
import datetime
import pytz
import itertools
from operator import itemgetter
from influxdb import InfluxDBClient


# read the configuration file
execfile('flows.conf')


class Flow_Consumer():

  def connect_influxdb(self):
    try:
      self.idb = InfluxDBClient(idb['host'], idb['port'], idb['user'], idb['passwd'], idb['db'])
    except:
      print('Error connecting influxdb')

  def write_influxdb(self, measurement, tags, time, fields):
    local_dt = localts.localize(time, is_dst=None)
    utc_dt = local_dt.astimezone(pytz.utc)
    json = [{'measurement': measurement, 'tags': tags, 'time': utc_dt, 'fields': fields}]
    try:
      #print('writing point to influxdb: {}'.format(json))
      self.idb.write_points(json)
    except:
      print('influxdb update failed for {}'.format(json))

  def consume_data(self, channel, method, properties, body):
    print('amqp consume data on {}'.format(method.routing_key))
    data = json.loads(body)
    if method.routing_key == 'if-in-all': 
      self.process_ifstats('if-in', data)
    elif method.routing_key == 'if-in-byif': 
      self.process_ifstats_byif('if-in', data)
    elif method.routing_key == 'if-in-bycust':
      self.process_ifstats_bycust('if-in', data)
    elif method.routing_key == 'if-out-all':
      self.process_ifstats('if-out', data)
    elif method.routing_key == 'if-out-byif':
      self.process_ifstats_byif('if-out', data)
    elif method.routing_key == 'if-out-bycust':
      self.process_ifstats_bycust('if-out', data)
    elif method.routing_key == 'asn-in':
      self.process_asnstats('asn-in', 'as_src', data)
    elif method.routing_key == 'asn-out':
      self.process_asnstats('asn-out', 'as_dst', data)

  def process_asnstats(self, metric, direction, data):
    ts = datetime.datetime.now()
    for line in data:
      asn = line[direction]
      bps = float(line['bytes']*8*sampling/interval)
      pps = float(line['packets']*sampling/interval)
      ts = datetime.datetime.strptime(line['stamp_updated'], '%Y-%m-%d %H:%M:%S')
      self.write_influxdb(metric, {'asn':asn,'customer':'all'}, ts, {'bps':bps,'pps':pps})

  def process_ifstats(self, metric, data):
    ts = datetime.datetime.now()
    for line in data:
      interface = interfaces_map[line['tag']]
      router = routers_map[line['tag']]
      cust = custs_map[line['tag2']]
      bps = float(line['bytes']*8*sampling/interval)
      pps = float(line['packets']*sampling/interval)
      ts = datetime.datetime.strptime(line['stamp_updated'], '%Y-%m-%d %H:%M:%S')
      self.write_influxdb(metric, {'interface':interface,'router':router,'customer':cust}, ts, {'bps':bps,'pps':pps})

  def process_ifstats_byif(self, metric, data):
    total_bps = 0
    total_pps = 0
    ts = datetime.datetime.now()
    for line in data:
      bps = float(line['bytes']*8*sampling/interval)
      pps = float(line['packets']*sampling/interval)
      interface = interfaces_map[line['tag']]
      router = routers_map[line['tag']]
      ts = datetime.datetime.strptime(line['stamp_updated'], '%Y-%m-%d %H:%M:%S')
      total_bps += bps
      total_pps += pps
      self.write_influxdb(metric, {'interface':interface,'router':router,'customer':'all'}, ts, {'bps':bps,'pps':pps})
    self.write_influxdb(metric, {'interface':'any','router':'any','customer':'all'}, ts, {'bps':total_bps,'pps':total_pps})

  def process_ifstats_bycust(self, metric, data):
    ts = datetime.datetime.now()
    for line in data:
      bps = float(line['bytes']*8*sampling/interval)
      pps = float(line['packets']*sampling/interval)
      cust = custs_map[line['tag2']]
      ts = datetime.datetime.strptime(line['stamp_updated'], '%Y-%m-%d %H:%M:%S')
      self.write_influxdb(metric, {'interface':'any','router':'any','customer':cust}, ts, {'bps':bps,'pps':pps})

  def __init__(self):
    self.amqp_host = "localhost"
    self.amqp_exchange = 'pmacct'
    self.connect_influxdb()
    self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.amqp_host))
    self.channel = self.connection.channel()
    self.channel.exchange_declare(exchange=self.amqp_exchange, type='direct')
    for exchange in exchanges:
      result = self.channel.queue_declare(exclusive=True)
      queue_name = result.method.queue
      self.channel.queue_bind(exchange=self.amqp_exchange, routing_key=exchange, queue=queue_name)
      print('waiting for messages on exchange={} routing-key={}'.format(self.amqp_exchange,exchange))
      self.channel.basic_consume(self.consume_data, queue=queue_name, no_ack=True)
    self.channel.start_consuming()

   
if __name__ == "__main__":
  flow = Flow_Consumer() 
  
