"""
Elastic Beanstalk entry point - exposes FastAPI app as 'application'
"""
from main import app

# Beanstalk expects the WSGI app to be named 'application'
application = app
