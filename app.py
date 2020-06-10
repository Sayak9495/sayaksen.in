import os
from flask import Flask, render_template, jsonify, request, url_for, send_from_directory, flash, send_file, redirect, g, session
from pymongo import MongoClient
import json
import time
import datetime
import urllib.parse
import io

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from flask_ckeditor import CKEditor, CKEditorField, upload_fail, upload_success

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['CKEDITOR_SERVE_LOCAL'] = True
app.config['CKEDITOR_PKG_TYPE'] = 'full'
app.config['CKEDITOR_HEIGHT'] = 400
app.config['CKEDITOR_FILE_UPLOADER'] = 'upload'
app.config['UPLOADED_PATH'] = os.path.join(basedir, 'images')
ckeditor = CKEditor(app)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

client = MongoClient(os.environ["MONGO_URI"])
db = client["sayaksenBlog"]
blogListCollection = db["blogList"]
blogsCollection = db["blogs"]
imgCollection = db["images"]
ipCollection = db["ip"]
totalViewCollection = db["totalView"]

# BEFORE
@app.before_request
def before_request():
	g.email = None
	if 'email' in session:
		g.email = session['email']

# Favicon
@app.route('/favicon.ico')
def favicon():
	return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico',mimetype='image/vnd.microsoft.icon')

# Landing Page
@app.route("/")
def index():
	save_ip()
	return render_template('index.html')

# BlogSpace
@app.route("/blogSpace")
def blogSpace():
	save_ip()
	return render_template('blogList.html', posts=blogList('blog'), space='blog')

# WorkSpace
@app.route("/workSpace")
def workSpace():
	save_ip()
	return render_template('blogList.html', posts=blogList('work'), space='work')

def blogList(target):
	if (request.args.get('tags')):
		tags = [tag.strip() for tag in request.args.get('tags').split(',')]
		posts = list(blogListCollection.find({"$and": [{'target': target }, {'tags': {'$all' : tags }}]}))
	else:
		posts = list(blogListCollection.find({'target': target }))
	return posts[::-1]

# BlogView
@app.route("/blog/<postId>")
def blog(postId):
	save_ip()
	post = blogsCollection.find_one({"_id": postId})
	if (post == None):
		return render_template('404.html')
	result = blogListCollection.update_one({'_id': postId}, {'$inc': {'views': 1}})
	return render_template('blog.html', post=post, url=urllib.parse.quote(request.url, safe=''))


# Publish Code
class PostForm(FlaskForm):
	title = StringField('Title')
	description = StringField('Description')
	target = SelectField(choices=[('blog','blog'), ('work','work')])
	tags = StringField('Tags')
	body = CKEditorField('Body')
	txt = StringField()
	submit = SubmitField('Submit')


@app.route("/publish", methods=['GET', 'POST'])
def publish():
	if not g.email:
		return redirect('/')

	form = PostForm()
	if form.validate_on_submit():
		title = form.title.data
		description = form.description.data
		target = form.target.data
		tags = form.tags.data
		blog = form.body.data
		txt = form.txt.data
		if (txt != os.environ["FLASK_SECRET_KEY"]):
			print(txt, os.environ["FLASK_SECRET_KEY"])
			return render_template('publish.html', form=form)

		_id = target+'_'+str(int(time.time()))
		
		result = blogListCollection.insert_one({
			'_id': _id,
			'title': title,
			'description': description,
			'tags': [tag.strip() for tag in tags.split(',')],
			'created': str(datetime.datetime.now().date()),
			'views': 1,
			'target': target
			})
		
		result = blogsCollection.insert_one({
			'_id': _id,
			'blog': blog
			})

		return redirect('/blog/'+_id)
		
	return render_template('publish.html', form=form)

@app.route('/images/<filename>')
def uploaded_files(filename):
	img = imgCollection.find_one({"_id": urllib.parse.quote(filename)})
	return send_file(io.BytesIO(img['img']), mimetype='image/jpeg')


@app.route('/upload', methods=['POST'])
def upload():
	if not g.email:
		return redirect('/admin')

	f = request.files.get('upload')
	f_ = request.files['upload']

	extension = f.filename.split('.')[-1].lower()
	if extension not in ['jpg', 'gif', 'png', 'jpeg']:
		return upload_fail(message='Image only!')
	
	imgCollection.save({'_id': urllib.parse.quote(f.filename), 'img': f_.read()})

	url = url_for('uploaded_files', filename=f.filename)
	return upload_success(url=url)


# ADMIN
@app.route("/admin", methods=['GET', 'POST'])
def login():
	if g.email:
		return redirect('/')
	if (request.method == 'POST'):
		session.pop('email', None)
		email = request.form['email']
		password = request.form['password']

		# Just a layer of protection for CRM purposes.
		if (email == os.environ['ADMIN_EMAIL'] and password == os.environ['ADMIN_PASSWORD']):
			session['email'] = email
			return redirect('/')
		else:
			return render_template('login.html', message="Wrong Credentials!")

	return render_template('login.html')

# Analytics
def save_ip():
	if (ipCollection.find_one({ '_id': request.remote_addr}) == None):
		rslt = ipCollection.insert_one({ '_id': request.remote_addr, 'count':1 })
	else:
		ipCollection.update_one({ '_id': request.remote_addr}, {'$inc': {'count': 1}})
	totalViewCollection.update_one({'_id': "sayaksen.in",}, {'$inc': {'count': 1}})
# END

if __name__ == "__main__":
	app.run(host='0.0.0.0', debug=True)