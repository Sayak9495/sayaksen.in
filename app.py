import os
from flask import Flask, render_template, jsonify, request, url_for, send_from_directory, flash, send_file, redirect, g, session
from pymongo import MongoClient
import json
import time
import datetime
import urllib.parse
import io
import sched, threading

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
weeklyStatsCollection = db["weeklyStats"]

# This scheduler is for updating weekly stats 
schedule = sched.scheduler(time.time, time.sleep)

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
	save_analytics()
	return render_template('index.html', title='Sayak Sen- Blog of a noob techie')

# BlogSpace
@app.route("/blogSpace")
def blogSpace():
	save_analytics()
	return render_template('blogList.html', posts=blogList('blog'), space='blog', title="Sayak's BlogSpace")

# WorkSpace
@app.route("/workSpace")
def workSpace():
	save_analytics()
	return render_template('blogList.html', posts=blogList('work'), space='work', title="Sayak's WorkSpace")

# noneSpace
@app.route("/noneSpace")
def noneSpace():
	save_analytics()
	if not g.email:
		return redirect('/')
	return render_template('blogList.html', posts=blogList('none'), space='work', title="Sayak's NoneSpace")


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
	save_analytics()
	post = blogsCollection.find_one({"_id": postId})
	if (post == None):
		return render_template('404.html'),404
	result = blogListCollection.update_one({'_id': postId}, {'$inc': {'views': 1}})
	title = post['title'] if 'title' in post else 'Sayak Sen Blogs'
	return render_template('blog.html', post=post, url=urllib.parse.quote(request.url, safe=''), title=title)

# BlogView
@app.route("/resume")
def resume():
	save_analytics('resume')
	return app.send_static_file('resume/resume.pdf')

@app.errorhandler(404)
def not_found(e):
	return render_template("404.html", title="Not Found"),404

# Robots
@app.route('/robots.txt')
@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])

# Publish Blog
class PostForm(FlaskForm):
	title = StringField('Title')
	description = StringField('Description')
	target = SelectField(choices=[('blog','blog'), ('work','work'), ('none','none')])
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
			return render_template('publish.html', form=form, title='Publish Blogs')

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
			'title': title,
			'blog': blog
			})

		return redirect('/blog/'+_id)
		
	return render_template('publish.html', form=form, title='Publish Blogs')

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
			return render_template('login.html', message="Wrong Credentials!", title="Admin Page")

	return render_template('login.html', title="Login Page")

# Analytics
def save_analytics(resume=None):
	totalViewCollection.update_one({'_id': "sayaksen.in",}, {'$inc': {'count': 1}})
	if (resume):
		totalViewCollection.update_one({'_id': "resume",}, {'$inc': {'count': 1}})

def schedule_weeklyStats():
    schedule.enter(1, 1, weeklyStats, (schedule,))
    schedule.run()

def weeklyStats(sc):
	# get current date-time
	# if current date is saturday
	# data - 
	# 1. cumalitave data of blosList
	# 2. and week-wise data of stats
	# then get the earlier data from mongo
	# subtract cumaltive data and wee-wise data
	# send data to week-wise collection
	#  
	posts = list(blogListCollection.find())
	count = 0
	for post in posts:
		count += post['views']
	rslt = weeklyStatsCollection.insert_one({ 'date': datetime.datetime.utcnow(), 'count':count })
	schedule.enter(10, 1, weeklyStats, (sc,))
	# return str(count)

# END



if __name__ == "__main__":
	# threading.Thread(target=schedule_weeklyStats).start()
	app.run(host='0.0.0.0', debug=True)