#!/usr/bin/python3

import asyncio
import time
import socket
import argparse

import aiohttp

class MyConnector(aiohttp.TCPConnector):
  def __init__(self, ip):
    self.__ip = ip
    super().__init__()

  async def _resolve_host(
    self, host: str, port: int,
    traces: None = None,
  ):
    return [{
      'hostname': host, 'host': self.__ip, 'port': port,
      'family': self._family, 'proto': 0, 'flags': 0,
    }]

async def test_domain(domain, ip, proto):
  if proto == 'http':
    return await test_domain_http(domain, ip)
  elif proto == 'ssh':
    return await test_domain_ssh(domain, ip)
  else:
    raise ValueError('unknown proto', proto)

async def test_domain_ssh(domain, ip):
  st = time.time()
  r, _w = await asyncio.open_connection(ip, 22)
  await r.read(1)
  return time.time() - st

async def test_domain_http(domain, ip):
  url = 'https://github.com/'
  st = time.time()
  async with aiohttp.ClientSession(
    connector = MyConnector(ip),
    timeout = aiohttp.ClientTimeout(total=10),
  ) as s:
    r = await s.get(url)
    _ = await r.text()

  return time.time() - st

async def producer(q, proto):
  items = await get_items(proto)
  for item in items:
    await q.put(item)

  await q.put(None)

async def printer(q):
  while True:
    try:
      item = await q.get()
    except asyncio.CancelledError:
      break

    if isinstance(item[1], Exception):
      (domain, ip, proto), e = item
      print(f'{domain:21} {ip:15} {proto:4} {e!r}')
    else:
      (domain, ip, proto), t = item
      print(f'{domain:21} {ip:15} {proto:4} {t:6.2f}')

async def fastest_finder(q):
  fastest_ip, latency = None, 1000

  while True:
    try:
      item = await q.get()
    except asyncio.CancelledError:
      return fastest_ip

    if not isinstance(item[1], Exception):
      (_, ip, _), t = item
      if t < latency:
        latency = t
        fastest_ip = ip

async def worker(q, ret_q):
  while True:
    item = await q.get()
    if item is None:
      await q.put(None)
      break

    try:
      t = await test_domain(*item)
    except Exception as e:
      await ret_q.put((item, e))
    else:
      await ret_q.put((item, t))

async def main(proto):
  q = asyncio.Queue()
  ret_q = asyncio.Queue()

  futures = [worker(q, ret_q) for _ in range(40)]
  producer_fu = asyncio.ensure_future(producer(q, proto))
  printer_fu = asyncio.ensure_future(printer(ret_q))

  await asyncio.gather(*futures)
  printer_fu.cancel()
  await producer_fu
  await printer_fu

async def update_hosts():
  import os, sys, subprocess

  if os.geteuid() != 0:
    sys.exit('not root?')

  q = asyncio.Queue()
  ret_q = asyncio.Queue()

  futures = [worker(q, ret_q) for _ in range(40)]
  producer_fu = asyncio.ensure_future(
    producer(q, ['http']))
  finder_fu = asyncio.ensure_future(
    fastest_finder(ret_q))

  await asyncio.gather(*futures)
  finder_fu.cancel()
  await producer_fu
  ip = await finder_fu

  if ip is not None:
    cmd = ['sed', '-Ei', rf'/^[0-9.]+[[:space:]]+(gist\.)?github\.com\>/s/[^[:space:]]+/{ip}/', '/etc/hosts']
    subprocess.check_call(cmd)

async def resolve(domain):
  loop = asyncio.get_event_loop()
  addrinfo = await loop.getaddrinfo(
    domain, None,
    family=socket.AF_INET,
    proto=socket.IPPROTO_TCP,
  )
  ips = [x[-1][0] for x in addrinfo]
  return domain, ips

async def get_items(proto):
  items = [
    ('13.234.210.38',  'Bombay'),
    ('13.234.176.102', 'Bombay'),
    ('52.192.72.89',   'Tokyo'),
    ('13.114.40.48',   'Tokyo'),
    ('52.69.186.44',   'Tokyo'),
    ('15.164.81.167',  'Seoul'),
    ('52.78.231.108',  'Seoul'),
    ('13.229.188.59',  'Singapore'),
    ('13.250.177.223', 'Singapore'),
    ('52.74.223.119',  'Singapore'),
    ('192.30.255.112', 'Seattle'),
    ('192.30.255.113', 'Seattle'),
    ('140.82.112.3',   'Seattle'),
    ('140.82.112.4',   'Seattle'),
    ('192.30.253.112', 'Ashburn'),
    ('192.30.253.113', 'Ashburn'),
    ('140.82.113.3',   'Ashburn'),
    ('140.82.113.4',   'Ashburn'),
    ('140.82.114.3',   'Ashburn'),
    ('140.82.114.4',   'Ashburn'),
    ('140.82.118.3',   'Armsterdam'),
    ('140.82.118.4',   'Armsterdam'),
    ('140.82.121.3',   'Frankfurt'),
    ('140.82.121.4',   'Frankfurt'),
    ('13.237.44.5',    'Sydney'),
    ('52.64.108.95',   'Sydney'),
    ('13.236.229.21',  'Sydney'),
    ('18.231.5.6',     'Sao Paulo'),
    ('18.228.52.138',  'Sao Paulo'),
    ('18.228.67.229',  'Sao Paulo'),
  ]

  return [(x[1], x[0], y) for x in items for y in proto]

if __name__ == '__main__':
  import logging
  logging.getLogger().addHandler(logging.NullHandler())

  parser = argparse.ArgumentParser(
    description='GitHub IP 访问速度测试')
  parser.add_argument('proto', nargs='*',
                      default=['http', 'ssh'],
                      help='测试指定协议')
  parser.add_argument('--hosts',
                      action='store_true',
                      help='更新 /etc/hosts')
  args = parser.parse_args()

  if args.hosts:
    main_fu = update_hosts()
  else:
    main_fu = main(args.proto)

  loop = asyncio.get_event_loop()
  try:
    loop.run_until_complete(main_fu)
  except KeyboardInterrupt:
    pass
