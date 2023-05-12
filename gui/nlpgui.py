#!/usr/bin/env python3

import bottle
from bottle import static_file, run, template, request
import subprocess

port = 8090

app = bottle.Bottle()


@app.route('/<filename:path>')
def serve_static(filename):
    return static_file(filename, root='public/')


def index():
    return template("index", passage="", result=None)


def parse():
    passage = request.forms.get("passage")

    result = {
        "answer": None,
        "raw": None
    }

    # "-usekb", "cnet_50k.js",

    cmd = subprocess.run(["python3", "nlpsolver.py", passage, "--debug", "--simple", "--explain"], stdout=subprocess.PIPE)
    result["raw"] = str(cmd.stdout, 'utf-8')

    cmd = subprocess.run(["python3", "nlpsolver.py", passage], stdout=subprocess.PIPE)
    result["answer"] = str(cmd.stdout, 'utf-8')

    return template("index", passage=passage, result=result)


def setup_routing(app):
    app.route("/", "GET", index)
    app.route("/", "POST", parse)


setup_routing(app)

if __name__ == "__main__":
    run(host="localhost", port=port, app=app, debug=True, reloader=True)