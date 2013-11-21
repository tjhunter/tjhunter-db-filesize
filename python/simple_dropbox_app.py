# -*- coding: utf-8 -*-
"""
An example of Dropbox App linking with Flask.
"""

import os
import posixpath
import locale
from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, _app_ctx_stack

from dropbox.client import DropboxClient, DropboxOAuth2Flow

import logging
from myapp import get_users_shelve, get_files_shelve, run_update, path_key,UserInfo
from utils import pretty_print_size

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(module)s/%(funcName)s: %(message)s')


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
  if not hasattr(top,'users_store'):
    logging.debug("Opening users shelve")
    users = get_users_shelve()
    top.users_store = users
  return top.users_store

def get_files_store():
  top = _app_ctx_stack.top
  if not hasattr(top,'files_store'):
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

def get_client():
    access_token = get_access_token()
    client = None
    if access_token is not None:
        client = DropboxClient(access_token)
    return client

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    access_token = get_access_token()
    real_name = None
    if access_token is not None:
        client = DropboxClient(access_token)
        account_info = client.account_info()
        real_name = account_info["display_name"]
    return render_template('index.html', real_name=real_name)

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
    #redirect_uri = url_for('dropbox_auth_finish', _external=False)
    redirect_uri = "http://localhost:5000/dropbox-auth-finish"
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
  client  = get_client()
  logging.debug("Running delta update")
  users = get_users_store()
  files = get_files_store()
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
          full_path = (u"/%s/%s"%(pathname,name)).replace("//",'/')
          logging.debug("Full path: %r, pathname: %r, name: %r", full_path, pathname, name)
          key = path_key(uid, full_path.lower().split("/"))
          size = 0
          if key in files:
            size = files[key]
          else:
            logging.warning("Could not find key %r in files",key)
          display_size = pretty_print_size(abs(size))
          is_dir = f['is_dir']
          # Need to remove an extra "/" prefix
          inner_link = url_for('get_route',uid=uid,pathname=full_path[1:]) if is_dir else ""
          db_link = u"http://www.dropbox.com/home%s"%full_path
          logging.debug("path: %r",name)
          data.append({'path':name,
                       'size':size,
                       'is_dir':is_dir,
                       'inner_link':inner_link,
                       'db_link':db_link,
                       'display_size':display_size})
  flash("You want to see %r, %r"%(uid, pathname))
  display_path = formatted_path_name or "home directory"
  logging.debug(data)
  return render_template('view.html', dir_name=display_path,
                         dir_content=data)

@app.route('/view/<uid>')
@app.route('/view/<uid>/')
def get_route_root(uid):
  logging.debug("Got uid %r",uid)
  return get_route(uid, u'')

def main():
    init_db()
    #app.run()
    app.run(host='0.0.0.0')


if __name__ == '__main__':
    main()
