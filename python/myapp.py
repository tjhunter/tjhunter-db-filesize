__author__ = 'tjhunter'
from collections import  namedtuple
import shelve
import logging
import dropbox
import sys
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(module)s/%(funcName)s: %(message)s')
#def excepthook(*args):
#    logging.getLogger().error('Uncaught exception:', exc_info=args)
#sys.excepthook = excepthook
#
class UserInfo(namedtuple("UserInfo",['uid','token', 'cursor'],verbose=True)):
  pass

#from operator import  itemgetter
#_property = property
#_tuple = tuple
#_itemgetter = itemgetter
#
#
#class UserInfo(tuple):
#        'UserInfo(uid, token, cursor)'
#
#        __slots__ = ()
#
#        _fields = ('uid', 'token', 'cursor')
#
#        def __new__(_cls, uid, token, cursor):
#            'Create new instance of UserInfo(uid, token, cursor)'
#            return _tuple.__new__(_cls, (uid, token, cursor))
#
#        @classmethod
#        def _make(cls, iterable, new=tuple.__new__, len=len):
#            'Make a new UserInfo object from a sequence or iterable'
#            result = new(cls, iterable)
#            if len(result) != 3:
#                raise TypeError('Expected 3 arguments, got %d' % len(result))
#            return result
#
#        def __repr__(self):
#            'Return a nicely formatted representation string'
#            return 'UserInfo(uid=%r, token=%r, cursor=%r)' % self
#
#        def _asdict(self):
#            'Return a new OrderedDict which maps field names to their values'
#            return OrderedDict(zip(self._fields, self))
#
#        __dict__ = property(_asdict)
#
#        def _replace(_self, **kwds):
#            'Return a new UserInfo object replacing specified fields with new values'
#            result = _self._make(map(kwds.pop, ('uid', 'token', 'cursor'), _self))
#            if kwds:
#                raise ValueError('Got unexpected field names: %r' % kwds.keys())
#            return result
#
#        def __getnewargs__(self):
#            'Return self as a plain tuple.  Used by copy and pickle.'
#            return tuple(self)
#
#        uid = _property(_itemgetter(0), doc='Alias for field number 0')
#        token = _property(_itemgetter(1), doc='Alias for field number 1')
#        cursor = _property(_itemgetter(2), doc='Alias for field number 2')

def get_users_shelve():
  fname = "users"
  d = shelve.open(fname)
  return d

def get_files_shelve():
  fname = "files"
  d = shelve.open(fname)
  return d

def insert_dummy_user(users):
  tim = UserInfo(str(1448704), "6B3KrFN1Z0MAAAAAAAAAAcIVY9D5tA_XzpMwk9I0HxjoQNKv80dJ02h1oeoLwikW", None)
  users[tim.uid] = tim

def path_key(uid, path):
  return (u"%s-%s"%(str(uid),u"/".join(path))).encode('utf8')

def reset_users_files(uid):
  files = get_files_shelve()
  for key in files.iterkeys():
    if key.startswith(str(uid)):
      files[key] = 0

def change_file_internal(uid, path, size, files):
  key = path_key(uid, path)
  if key not in files:
    files[key] = 0
  files[key] += size
  #logging.debug("Set %r -> %r (%r)", key, files[key], size)

def change_file(uid, path, size, files):
  # Set the leaf with the value of the file
  change_file_internal(uid, path, size, files)
  # Change the inner nodes with the opposite value to distinguish internal nodes and leaves.
  # The reverse order is for pretty print purpose
  for i in range(1,len(path))[::-1]:
    #logging.debug("Call on path %r", path[:i])
    change_file_internal(uid, path[:i], -size, files)

def set_file(uid, path, size, files):
  # Find the value of the leaf, if any:
  delta_size = size
  key = path_key(uid, path)
  #logging.info("key:%s",str(key))
  if key in files:
    delta_size = size - files[key]
  change_file(uid, path, delta_size, files)


def apply_delta(uid, delta_entry, files):
  #logging.info("Received for user %r delta %r", uid, delta_entry)
  (obj_name, meta) = delta_entry
  path = obj_name.split('/')
  key = path_key(uid, path)
  if meta is None:
    # We are deleting a file
    if key in files:
      prev_size = files[key]
      if prev_size > 0:
        # It is a non-zero leaf: update with the new size
        set_file(uid, path, 0, files)
        logging.info("Delete existing leaf: %r", key)
      if prev_size < 0:
        # It is an internal node: nothing to do
        logging.info("Skipping internal node delete: %r", key)
    else:
      logging.error("Trying to delete non-existing node: %r",key)
  else:
    # We are adding/updating a file
    size = meta[u'bytes']
    if key in files:
      prev_size = files[key]
      if prev_size > 0:
        # It is a non-zero leaf: update with the new size
        set_file(uid, path, size, files)
        logging.info("Update leaf: %r -> %r", key, size)
      if prev_size < 0:
        # It is an internal node: nothing to do
        logging.info("Skipping internal node update: %r -> %r", key, size)
    else:
      # It is a new leaf or internal node: insert
      set_file(uid, path, size, files)
      logging.info("New node: %r -> %r", key, size)

def run_update(client, uid, users, files, page_limit=None):
  page = 0
  changed = False
  while (page_limit is None) or (page < page_limit):
    cursor = users[uid].cursor
    # Get /delta results from Dropbox
    result = client.delta(cursor)
    #logging.info("Got delta %s", str(result))
    page += 1
    if result['reset'] == True:
        logging.info('reset user %r', uid)
        changed = True
        tree = {}
    cursor = result['cursor']
    # Apply the entries one by one to our cached tree.
    for delta_entry in result['entries']:
        changed = True
        apply_delta(uid, delta_entry, files)
    cursor = result['cursor']
    new_user_info = users[uid]._replace(cursor=cursor)
    users[uid] = new_user_info
    if not result['has_more']:
      logging.debug("Done with update")
      break

  logging.debug("Current content for users:")
  for user in users.itervalues():
    logging.debug("%r",user)
  logging.debug("Current content for files:")
  for (key, size) in sorted(files.items(),key=lambda z:z[0]):
    logging.debug("%r => %r", key, size)

#users = get_users_shelve()
#files = get_files_shelve()
#
#insert_dummy_user(users)
#
#uid = str(1448704)
#access_token = users[uid].token
#c = dropbox.client.DropboxClient(access_token)
