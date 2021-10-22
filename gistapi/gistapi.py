# coding=utf-8
"""
Exposes a simple HTTP API to search a users Gists via a regular expression.

Github provides the Gist service as a pastebin analog for sharing code and
other develpment artifacts.  See http://gist.github.com for details.  This
module implements a Flask server exposing two endpoints: a simple ping
endpoint to verify the server is up and responding and a search endpoint
providing a search across all public Gists for a given Github account.
"""

import re
import requests
from flask import Flask, abort, jsonify, request
from marshmallow import Schema, fields, ValidationError


# *The* app object
app = Flask(__name__)


@app.route("/ping")
def ping():
    """Provide a static response to a simple GET request."""
    return "pong"


def gists_for_user(username,perPage=0):
    """Provides the list of gist metadata for a given user.

    This abstracts the /users/:username/gist endpoint from the Github API.
    See https://developer.github.com/v3/gists/#list-a-users-gists for
    more information.

    Args:
        username (string): the user to query gists for

    Returns:
        The dict parsed from the json response from the Github API.  See
        the above URL for details of the expected structure.
    """


    gists_url = 'https://api.github.com/users/{username}/gists'.format(
            username=username)

    response = requests.get(gists_url)
    result = []
    if perPage>0:
        if perPage>100:
            perPage=100 #maximum from git documentation
        else:
            perPage=perPage
        extra = '?per_page={perPage}&page='.format(perPage=perPage)
        fullUrl = gists_url + extra
        currentPage = 1
        while True:
            response = requests.get(fullUrl + str(currentPage))
            if response.status_code == 404:
                abort(404, description="No user found")
            elif response.json():
                currentPage += 1
                result.extend(response.json())
            else:
                break
    else:
        #default perPage is 30 according to documentation
        fullUrl=gists_url
        response = requests.get(fullUrl)
        result=response.json()

    return result

def check_user(username):
    # check if user exists
    userCheck = requests.get('https://api.github.com/users/{username}'.format(
        username=username))
    if userCheck.status_code == 404:
        return False
    return True


class QueryData(Schema):
    """
    Schema for validation
    """
    username = fields.String(required=True, allow_blank=False, allow_none=False)
    pattern = fields.String(required=True, allow_blank=False, allow_none=False)

@app.route("/api/v1/search", methods=['POST'])
def search():
    """Provides matches for a single pattern across a single users gists.

    Pulls down a list of all gists for a given user and then searches
    each gist for a given regular expression.

    Returns:
        A Flask Response object of type application/json.  The result
        object contains the list of matches along with a 'status' key
        indicating any failure conditions.
    """
    post_data = request.get_json()
    data = QueryData()
    chunkSize=1024
    # BONUS: Validate the arguments?
    try:
        data.load(post_data)
    except ValidationError as vErr:
        return jsonify(vErr.messages), 400

    username = post_data['username']
    pattern = post_data['pattern']

    result = {}

    if check_user(username):
        gists = gists_for_user(username)
        result = {'username': username, 'pattern': pattern}
        matches = []
        if not gists:
            status_code = 200
            # status is success but we don't have  gists
            result['status'] = 'no_gists'
            result['matches'] = matches
        else:
            try:
                for gist in gists:
                    # iterate over files and check for pattern
                    for file_name, content in gist.get('files', {}).items():
                        r = requests.get(content['raw_url'], stream=True)
                        #read partially
                        for contentChunk in r.iter_content(chunk_size=chunkSize):
                            if re.search(pattern.encode('utf-8'), contentChunk):
                                matches.append("/".join(["https://gist.github.com", username, gist['id']]))
                                # exit on first match
                                break

                result['status'] = 'success'
                result['matches'] = matches
                status_code = 200
            except Exception as e:
                result['status'] = 'failure'
                result['message'] = 'Internal server error'
                print(e)
                status_code = 500
    else:
        #status_code is success but there is no user
        result['status'] = 'error'
        result['message'] = 'No user {user} found'.format(user=username)
        result['matches'] =[]
        status_code = 200
    return jsonify(result), status_code


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9876)
