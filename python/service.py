__author__ = 'tjhunter'
# Taken from the flask example
import os
import posixpath

from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, _app_ctx_stack

from dropbox.client import DropboxClient, DropboxOAuth2Flow

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

def get_access_token():
    username = session.get('user')
    if username is None:
        return None
    db = get_db()
    row = db.execute('SELECT access_token FROM users WHERE username = ?', [username]).fetchone()
    if row is None:
        return None
    return row[0]

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    access_token = get_access_token()
    real_name = None
    print(access_token)
    if access_token is not None:
        client = DropboxClient(access_token)
        account_info = client.account_info()
        real_name = account_info["display_name"]
    return render_template('index.html', real_name=real_name)

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


def main():
    init_db()
    app.run()


if __name__ == '__main__':
    main()
