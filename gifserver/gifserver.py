#!/usr/bin/env python

# I TAKE NO CREDIT FOR THIS, FOUND ON STACK OVERFLOW
# http://stackoverflow.com/questions/10961378/how-to-generate-an-html-directory-list-using-python
# ADAPTED FOR MY NEEDS

import os
from flask import Flask, render_template

def make_tree(path):
    tree = dict(name=os.path.basename(path), children=[])
    try: lst = os.listdir(path)
    except OSError:
        pass #ignore errors
    else:
        for name in lst:
            fn = os.path.join(path, name)
            if os.path.isdir(fn):
                tree['children'].append(make_tree(fn))
            else:
                tree['children'].append(dict(name=fn))
    return tree

app = Flask(__name__, static_url_path="/root/gifserver/static", static_folder="/root/gifserver/static")

@app.route('/')
def dirtree():
    path = os.path.expanduser(u'/root/gifserver/static')
    return render_template('giftree.html', tree=make_tree(path))

if __name__=="__main__":
    app.run(host='0.0.0.0', port=80, debug=True)
