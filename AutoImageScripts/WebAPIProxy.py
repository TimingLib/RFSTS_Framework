import Queue as queue
import urlparse
import httplib
import urllib
import json

class WebAPIProxy(object):
   _connections = {}

   def __init__(self, baseURL):
      url = urlparse.urlsplit(baseURL)
      self._netloc = url.netloc
      self._path = url.path.rstrip('/') + '/'

   def __getattr__(self, name):
      def proxy_method(**kwargs):
         q = self._connections.setdefault(self._netloc, queue.Queue())
         try:
            conn = q.get(False)
         except queue.Empty:
            conn = httplib.HTTPConnection(self._netloc)

         if kwargs:
            conn.request('POST', self._path + name, urllib.urlencode(kwargs))
         else:
            conn.request('GET', self._path + name)

         res = conn.getresponse()
         body = res.read()
         q.put(conn)

         if res.getheader('content-type') == 'application/json':
            return json.loads(body)
         else:
            return body

      return proxy_method