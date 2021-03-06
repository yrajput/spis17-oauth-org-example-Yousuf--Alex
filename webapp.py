from flask import Flask, redirect, url_for, session, request, jsonify
from flask_oauthlib.client import OAuth
from flask import render_template, flash, Markup
from flask_pymongo import PyMongo
from werkzeug import secure_filename

from github import Github

import pprint
import os
import sys
import traceback
from PIL import Image

class GithubOAuthVarsNotDefined(Exception):
    '''raise this if the necessary env variables are not defined '''

if os.getenv('GITHUB_CLIENT_ID') == None or \
        os.getenv('GITHUB_CLIENT_SECRET') == None or \
        os.getenv('APP_SECRET_KEY') == None or \
        os.getenv('GITHUB_ORG') == None:
    raise GithubOAuthVarsNotDefined('''
      Please define environment variables:
         GITHUB_CLIENT_ID
         GITHUB_CLIENT_SECRET
         GITHUB_ORG
         APP_SECRET_KEY
      ''')

app = Flask(__name__)

app.debug = False

app.secret_key = os.environ['APP_SECRET_KEY']
oauth = OAuth(app)

# This code originally from https://github.com/lepture/flask-oauthlib/blob/master/example/github.py
# Edited by P. Conrad for SPIS 2016 to add getting Client Id and Secret from
# environment variables, so that this will work on Heroku.


github = oauth.remote_app(
    'github',
    consumer_key=os.environ['GITHUB_CLIENT_ID'],
    consumer_secret=os.environ['GITHUB_CLIENT_SECRET'],
    request_token_params={'scope': 'read:org'},
    base_url='https://api.github.com/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize'
)

app.config['MONGO_HOST'] = os.environ['MONGO_HOST']
app.config['MONGO_PORT'] = int(os.environ['MONGO_PORT']) 
app.config['MONGO_DBNAME'] = os.environ['MONGO_DBNAME']
app.config['MONGO_USERNAME'] = os.environ['MONGO_USERNAME']
app.config['MONGO_PASSWORD'] = os.environ['MONGO_PASSWORD']
mongo = PyMongo(app) 

UPLOAD_FOLDER = 'static/photos'
ALLOWED_EXTENTIONS = set(['jpg', 'JPG', 'jpeg', 'JPEG'])

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.context_processor
def inject_logged_in():
    return dict(logged_in=('github_token' in session))

@app.context_processor
def inject_github_org():
    return dict(github_org=os.getenv('GITHUB_ORG'))


@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login')
def login():
    return github.authorize(callback=url_for('authorized', _external=True, _scheme='https'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You were logged out')
    return redirect(url_for('home'))

@app.route('/login/authorized')
def authorized():
    resp = github.authorized_response()

    if resp is None:
        session.clear()
        login_error_message = 'Access denied: reason=%s error=%s full=%s' % (
            request.args['error'],
            request.args['error_description'],
            pprint.pformat(request.args)
        )        
        flash(login_error_message, 'error')
        return redirect(url_for('home'))    

    try:
        session['github_token'] = (resp['access_token'], '')
        session['user_data']=github.get('user').data
        github_userid = session['user_data']['login']
        org_name = os.getenv('GITHUB_ORG')
    except Exception as e:
        session.clear()
        message = 'Unable to login: ' + str(type(e)) + str(e)
        flash(message,'error')
        return redirect(url_for('home'))
    
    try:
        g = Github(resp['access_token'])
        org = g.get_organization(org_name)
        named_user = g.get_user(github_userid)
        isMember = org.has_in_members(named_user)
    except Exception as e:
        message = 'Unable to connect to Github with accessToken: ' + resp['access_token'] + " exception info: " + str(type(e)) + str(e)
        session.clear()
        flash(message,'error')
        return redirect(url_for('home'))
    
    if not isMember:
        session.clear() # Must clear session before adding flash message
        message = 'Unable to login: ' + github_userid + ' is not a member of ' + org_name + \
          '</p><p><a href="https://github.com/logout" target="_blank">Logout of github as user:  ' + github_userid + \
          '</a></p>' 
        flash(Markup(message),'error')

    else:
        flash('You were successfully logged in')

    return redirect(url_for('home'))    

@app.route('/page1')
def renderPage1():
  if not logged_in():
    flash("You must be logged in to continue.", 'error')
    return redirect(url_for('home'))
  arr = []
  login = session['user_data']['login']
  for doc in mongo.db.hangers.find({"user": login}):
      localpath = doc["path"]
      Image.frombytes('RGB', doc["size"], doc["encoded_string"]).save(localpath)
      arr.append(localpath)
  return render_template('page1.html', paths=arr)

@app.route('/page2')
def renderPage2():
    if not logged_in():
      flash("You must be logged in to continue.", 'error')
      return redirect(url_for('home'))
    return render_template('page2.html')

@app.route('/uploader', methods = ['GET', 'POST'])
def upload_file():
  github_userid = session['user_data']['login']
  if request.method == 'POST':
    f = request.files['file']
    f.save(secure_filename(f.filename))
    image = Image.open(secure_filename(f.filename))
    seasons = "seasons" in request.form
    parties = "parties" in request.form
    beach = "beach" in request.form
    professional = "professional" in request.form
    bar=[]
    if seasons == True:
      bar.append("seasons")
    if parties == True:
      bar.append("parties")
    if beach == True:
      bar.append("beach")
    if professional == True:
      bar.append("professional") 
    mongo.db.hangers.insert_one({"category":bar,"size":image.size,"encoded_string":image.tobytes(),"path":"static/photos/"+secure_filename(f.filename),"user":github_userid})
    flash("File uploaded successfully, redirecting to Closet")
    return redirect(url_for('renderPage1'))

@app.route('/page3')
def renderPage3():
    if not logged_in():
      flash("You must be logged in to continue.", 'error')
      return redirect(url_for('home'))
    arr = []
    login = session['user_data']['login']
    for doc in mongo.db.hangers.find({"user": login, "category": "seasons"}):
      localpath = doc["path"]
      Image.frombytes('RGB', doc["size"], doc["encoded_string"]).save(localpath)
      arr.append(localpath)
    return render_template('page3.html', paths=arr)

@app.route('/page4')
def renderPage4():
    if not logged_in():
      flash("You must be logged in to continue.", 'error')
      return redirect(url_for('home'))
    arr = []
    login = session['user_data']['login']
    for doc in mongo.db.hangers.find({"user": login, "category": "parties"}):
      localpath = doc["path"]
      Image.frombytes('RGB', doc["size"], doc["encoded_string"]).save(localpath)
      arr.append(localpath)
    return render_template('page4.html', paths=arr)

@app.route('/page5')
def renderPage5():
    if not logged_in():
      flash("You must be logged in to continue.", 'error')
      return redirect(url_for('home'))
    arr = []
    login = session['user_data']['login']
    for doc in mongo.db.hangers.find({"user": login, "category": "beach"}):
      localpath = doc["path"]
      Image.frombytes('RGB', doc["size"], doc["encoded_string"]).save(localpath)
      arr.append(localpath)
    return render_template('page5.html', paths=arr)


@app.route('/page6')
def renderPage6():
    if not logged_in():
      flash("You must be logged in to continue.", 'error')
      return redirect(url_for('home'))
    arr = []
    login = session['user_data']['login']
    for doc in mongo.db.hangers.find({"user": login, "category": "professional"}):
      localpath = doc["path"]
      Image.frombytes('RGB', doc["size"], doc["encoded_string"]).save(localpath)
      arr.append(localpath)
    return render_template('page6.html', paths=arr)

@github.tokengetter
def get_github_oauth_token():
    return session.get('github_token')

def logged_in():
  return 'github_token' in session

if __name__ == '__main__':
	app.run(port=5001)
