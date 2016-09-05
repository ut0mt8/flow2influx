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

#as-path-group golden-as {
#    as-path edgecast ".*15133$";
#    as-path limelight ".*22822$";
#    as-path akamai ".*20940$";
#    as-path ft ".*3215$";
#    as-path free ".*12322$";
#    as-path sfr ".*15557$";
#    as-path bytel ".*5410$";
#    as-path nc ".*21502$";

as_list = [ '15133', '22822', '20940', '3215', '12322', '15557', '5410', '21502' ]

class BGP_Consumer():

  def consume_data(self, channel, method, properties, body):
    data = json.loads(body)
    peer = data['peer_ip_src']
    if data.has_key('as_path'):
       asn = data['as_path'].split(" ")[-1:][0]
       if not data['bgp_nexthop'].startswith('10.1.1.'):
           self.fh_table[peer].write(str(data['ip_prefix']))
           self.fh_table[peer].write(','+data['bgp_nexthop'])
           self.fh_table[peer].write(','+data['as_path'])
           self.fh_table[peer].write(','+asn)
           self.fh_table[peer].write('\n')
           self.pfx_table[data['ip_prefix']] = asn
           if asn in as_list:
               self.goldenpfx_fh_table[peer].write(str(data['ip_prefix']))
               self.goldenpfx_fh_table[peer].write(','+data['bgp_nexthop'])
               self.goldenpfx_fh_table[peer].write(','+data['as_path'])
               self.goldenpfx_fh_table[peer].write(','+asn)
               self.goldenpfx_fh_table[peer].write('\n')
               print asn,'|',data['ip_prefix'], len(self.pfx_table)
    elif data.has_key('event_type') and data['event_type'] == 'dump_init':
      self.pfx_table = {}
      self.fh_table[peer] = open('/tmp/bgp-dump-'+peer+'.txt','w')
      self.goldenpfx_fh_table[peer] = open('/tmp/bgp-dump-golden-'+peer+'.txt','w')
    elif data.has_key('event_type') and data['event_type'] == 'dump_close':
      self.fh_table[peer].flush()
      self.fh_table[peer].close()
      self.goldenpfx_fh_table[peer].flush()
      self.goldenpfx_fh_table[peer].close()

  def __init__(self):
    self.amqp_host = "localhost"
    self.amqp_exchange = 'pmacct-bgp'
    self.fh_table = {}
    self.pfx_table = {}
    self.goldenpfx_fh_table = {}
    self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.amqp_host))
    self.channel = self.connection.channel()
    self.channel.exchange_declare(exchange=self.amqp_exchange, type='direct')
    result = self.channel.queue_declare(exclusive=True)
    queue_name = result.method.queue
    self.channel.queue_bind(exchange=self.amqp_exchange, routing_key='bgp-dump', queue=queue_name)
    print('waiting for messages on exchange={} routing-key={}'.format(self.amqp_exchange,'bgp-dump'))
    self.channel.basic_consume(self.consume_data, queue=queue_name, no_ack=True)
    self.channel.start_consuming()

   
if __name__ == "__main__":
  flow = BGP_Consumer() 
  
