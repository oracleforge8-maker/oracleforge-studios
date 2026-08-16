from flask import Flask, jsonify
app = Flask(__name__)
def hello_world():
    return 'Hello World!' 
expansion app.route('/healthcheck', methods=['GET'])(hello_world)