"""Tiny WSGI app used to test gunicorn's own request parsing (item 9)."""


def app(environ, start_response):
    body = environ["wsgi.input"].read()
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"len=%d" % len(body)]
