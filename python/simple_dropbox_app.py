# -*- coding: utf-8 -*-
"""
An example of Dropbox App linking with Flask.
"""

import os
import posixpath
import locale
from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session, g, redirect, url_for, abort, \
  render_template, flash, _app_ctx_stack, jsonify

from dropbox.client import DropboxClient, DropboxOAuth2Flow

import logging
from myapp import get_users_shelve, get_files_shelve, run_update, path_key, UserInfo
from utils import pretty_print_size

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(module)s/%(funcName)s: %(message)s')

from OpenSSL import SSL
context = SSL.Context(SSL.SSLv23_METHOD)
context.use_privatekey_file('ssl.key')
context.use_certificate_file('ssl.cert')

# configuration
DEBUG = True
DATABASE = 'myapp.db'
SECRET_KEY = 'development key'

# Fill these in!
DROPBOX_APP_KEY = 'o7jb6lfmya9cl1a'
DROPBOX_APP_SECRET = '5ki1fvq5r1y3tv9'

# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('FLASKR_SETTINGS', silent=True)

# Ensure instance directory exists.
try:
  os.makedirs(app.instance_path)
except OSError:
  pass


def init_db():
  """Creates the database tables."""
  with app.app_context():
    db = get_db()
    with app.open_resource("schema.sql", mode="r") as f:
      db.cursor().executescript(f.read())
    db.commit()


def get_db():
  """
  Opens a new database connection if there is none yet for the current application context.
  """
  top = _app_ctx_stack.top
  if not hasattr(top, 'sqlite_db'):
    sqlite_db = sqlite3.connect(os.path.join(app.instance_path, app.config['DATABASE']))
    sqlite_db.row_factory = sqlite3.Row
    top.sqlite_db = sqlite_db
  return top.sqlite_db


def get_users_store():
  top = _app_ctx_stack.top
  if not hasattr(top, 'users_store'):
    logging.debug("Opening users shelve")
    users = get_users_shelve()
    top.users_store = users
  return top.users_store


def get_files_store():
  top = _app_ctx_stack.top
  if not hasattr(top, 'files_store'):
    logging.debug("Opening files shelve")
    files = get_files_shelve()
    top.files_store = files
  return top.files_store


def get_access_token():
  username = session.get('user')
  if username is None:
    return None
  db = get_db()
  row = db.execute('SELECT access_token FROM users WHERE username = ?', [username]).fetchone()
  if row is None:
    return None
  return row[0]


def get_client(uid):
  # Passing the UID improves performance by not having to query the account info.
  access_token = get_access_token()
  logging.debug("Got access token")
  client = None
  if access_token is not None:
    client = DropboxClient(access_token)
    logging.debug("Created client")
    #uid = str(client.account_info()['uid'])
    #logging.debug("User uid is %r",uid)
    users = get_users_store()
    if uid not in users:
      logging.debug("Inserting user %r", uid)
      users[uid] = UserInfo(uid,access_token,None)
    else:
      old_token = users[uid].token
      if old_token is None or old_token != access_token:
        # Update the access token for the user.
        new_user = users[uid]._replace(token=access_token)
        users[uid] = new_user
        logging.debug("Updated acces token for user %r",uid)
  return client


@app.route('/')
def home():
  if 'user' not in session:
    return redirect(url_for('login'))
  access_token = get_access_token()
  real_name = None
  uid = None
  if access_token is not None:
    client = DropboxClient(access_token)
    account_info = client.account_info()
    real_name = account_info["display_name"]
    uid = str(client.account_info()['uid'])
  if real_name is None:
    return render_template('index.html', real_name=real_name)
  else:
    return redirect(url_for('get_route_root',uid=uid))


@app.route('/dropbox-auth-finish')
def dropbox_auth_finish():
  username = session.get('user')
  if username is None:
    abort(403)
  try:
    access_token, user_id, url_state = get_auth_flow().finish(request.args)
  except DropboxOAuth2Flow.BadRequestException, e:
    abort(400)
  except DropboxOAuth2Flow.BadStateException, e:
    abort(400)
  except DropboxOAuth2Flow.CsrfException, e:
    abort(403)
  except DropboxOAuth2Flow.NotApprovedException, e:
    flash('Not approved?  Why not, bro?')
    return redirect(url_for('home'))
  except DropboxOAuth2Flow.ProviderException, e:
    app.logger.exception("Auth error" + e)
    abort(403)
  db = get_db()
  data = [access_token, username]
  db.execute('UPDATE users SET access_token = ? WHERE username = ?', data)
  db.commit()
  return redirect(url_for('home'))


@app.route('/dropbox-auth-start')
def dropbox_auth_start():
  if 'user' not in session:
    abort(403)
  return redirect(get_auth_flow().start())


@app.route('/dropbox-unlink')
def dropbox_unlink():
  username = session.get('user')
  if username is None:
    abort(403)
  db = get_db()
  db.execute('UPDATE users SET access_token = NULL WHERE username = ?', [username])
  db.commit()
  return redirect(url_for('home'))


def get_auth_flow():
  redirect_uri = url_for('dropbox_auth_finish', _external=True)
  #redirect_uri = "http://localhost:5000/dropbox-auth-finish"
  print "REDIRECT:"
  print redirect_uri
  return DropboxOAuth2Flow(DROPBOX_APP_KEY, DROPBOX_APP_SECRET, redirect_uri,
                           session, 'dropbox-auth-csrf-token')


@app.route('/login', methods=['GET', 'POST'])
def login():
  error = None
  if request.method == 'POST':
    username = request.form['username']
    if username:
      db = get_db()
      db.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', [username])
      db.commit()
      session['user'] = username
      flash('You were logged in')
      return redirect(url_for('home'))
    else:
      flash("You must provide a username")
  return render_template('login.html', error=error)


@app.route('/logout')
def logout():
  session.pop('user', None)
  flash('You were logged out')
  return redirect(url_for('home'))


@app.route('/view/<uid>/<path:pathname>')
def get_route(uid, pathname):
  logging.debug(pathname)
  client = get_client(str(uid))
  users = get_users_store()
  files = get_files_store()
  if 'refresh' in request.args and request.args['refresh'] == '1':
    logging.debug("Running delta update")
    run_update(client, str(uid), users, files)
    logging.debug("Done with delta update")
    # Remove the refresh argument so that the users do not refresh the cache when they
    # refresh the page.
    return redirect(url_for('get_route', uid=uid, pathname=pathname))
  formatted_path_name = pathname
  resp = client.metadata(formatted_path_name)
  logging.debug("Got metadata")
  #logging.debug(resp)
  data = []
  if 'contents' in resp:
    for f in resp['contents']:
      logging.debug(f)
      name = os.path.basename(f['path'])
      full_path = (u"/%s/%s" % (pathname, name)).replace("//", '/')
      logging.debug("Full path: %r, pathname: %r, name: %r", full_path, pathname, name)
      key = path_key(uid, full_path.lower().split("/"))
      size = 0
      if key in files:
        size = files[key]
      else:
        logging.warning("Could not find key %r in files", key)
      display_size = pretty_print_size(abs(size))
      is_dir = f['is_dir']
      # Need to remove an extra "/" prefix
      inner_link = url_for('get_route', uid=uid, pathname=full_path[1:]) if is_dir else ""
      db_link = u"http://www.dropbox.com/home%s" % full_path
      logging.debug("path: %r", name)
      data.append({'path': name,
                   'size': -abs(size),
                   'is_dir': is_dir,
                   'inner_link': inner_link,
                   'db_link': db_link,
                   'display_size': display_size})
  # Compute the normalized values
  sum_sizes = sum(elt['size'] for elt in data)
  for elt in data:
    elt['normalizedsize'] = min(int((100 * elt['size']) / sum_sizes)+1,100)
  dir_db_link = u"http://www.dropbox.com/home/%s" % pathname
  display_path = formatted_path_name or "home directory"
  back_link = url_for('get_route', uid=uid, pathname="/".join(pathname.split('/')[:-1])) if formatted_path_name else None
  logging.debug(data)
  return render_template('view.html',
                         dir_name=display_path,
                         dir_content=data,
                         dir_db_link=dir_db_link,
                         back_link=back_link,
                         ajax_link=url_for('get_route2', uid=uid, pathname=pathname),
                         refresh_link=url_for('get_route', uid=uid, pathname=pathname))


@app.route('/view2/<uid>/<path:pathname>')
def get_route2(uid, pathname):
  logging.debug(pathname)
  return render_template('view_ajax.html',
                         uid=uid, pathname=pathname)

@app.route('/view2/<uid>')
@app.route('/view2/<uid>/')
def get_route2_root(uid):
  return get_route2(uid, u'')


# Horrible copy/paste from the previous method, should be cleaned up
@app.route('/api/data_path')
def get_data_path():
  logging.debug("Processing request with arguments %r",request.args)
  uid = str(request.args.get('uid'))
  pathname = request.args.get('pathname')
  logging.debug("Data for %r",pathname)
  client = get_client(uid)
  users = get_users_store()
  files = get_files_store()
  logging.debug("Running delta update")
  run_update(client, str(uid), users, files)
  logging.debug("Done with delta update")
  formatted_path_name = pathname
  resp = client.metadata(formatted_path_name)
  logging.debug(resp)
  data = []
  if 'contents' in resp:
    for f in resp['contents']:
      logging.debug(f)
      name = os.path.basename(f['path'])
      full_path = (u"/%s/%s" % (pathname, name)).replace("//", '/')
      logging.debug("Full path: %r, pathname: %r, name: %r", full_path, pathname, name)
      key = path_key(uid, full_path.lower().split("/"))
      size = 0
      if key in files:
        size = files[key]
      else:
        logging.warning("Could not find key %r in files", key)
      display_size = pretty_print_size(abs(size))
      is_dir = f['is_dir']
      # Need to remove an extra "/" prefix
      inner_link = url_for('get_route', uid=uid, pathname=full_path[1:]) if is_dir else ""
      db_link = u"http://www.dropbox.com/home%s" % full_path
      logging.debug("path: %r", name)
      data.append({'path': name,
                   'size': -abs(size),
                   'is_dir': is_dir,
                   'inner_link': inner_link,
                   'db_link': db_link,
                   'display_size': display_size})
  # Compute the normalized values
  # Moke sure there it is > 0
  sum_sizes = sum(elt['size'] for elt in data) + 1
  for elt in data:
    elt['normalizedsize'] = min(int((100 * elt['size']) / sum_sizes)+1,100)
  #flash("You want to see %r, %r" % (uid, pathname))
  display_path = formatted_path_name or "home directory"
  back_link = url_for('get_route', uid=uid, pathname="/".join(pathname.split('/')[:-1])) if formatted_path_name else None
  logging.debug(data)
  return_data = dict(dir_name=display_path,
                         dir_content=data,
                         back_link=back_link,
                         refresh_link=url_for('get_route', uid=uid, pathname=pathname))
  return jsonify(return_data)

@app.route('/view/<uid>')
@app.route('/view/<uid>/')
def get_route_root(uid):
  logging.debug("Got uid %r", uid)
  return get_route(uid, u'')


def main():
  init_db()
  #app.run()
  app.run(host='0.0.0.0',debug = True, ssl_context=context)


if __name__ == '__main__':
  main()
