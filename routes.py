import requests
import sys
from collections import Counter
from models import *
from flask import json
from flask import Flask, Response, jsonify, abort, make_response, request, g, send_from_directory
from flask_restful import Resource, Api, reqparse, inputs
from flask_httpauth import HTTPBasicAuth
from config import app, session, port_num, consumer_key, consumer_secret
from werkzeug.exceptions import Unauthorized

auth = HTTPBasicAuth()
my_api = Api(app)

class UserInfo(Resource):
    def __init__(self):
        # used for posting new user information
        self.match_reqparse = reqparse.RequestParser()
        self.match_reqparse.add_argument('eventKey', type=str, location='json', required=True)
        self.match_reqparse.add_argument('image', type=str, location='json', required=True)
        self.match_reqparse.add_argument('previousIds', type=int, location='json', required=True, action='append')

        self.post_reqparse = reqparse.RequestParser()
        self.post_reqparse.add_argument('linkedinInfo', type=dict, location='json', required=False)
        self.post_reqparse.add_argument('eventKey', type=str, location='json', required=False)

    def put(self):
        params = self.match_reqparse.parse_args()
        print((params['previousIds']))
        event_id = session.query(Event).filter_by(event_key = params['eventKey']).first().as_dict()['eventId']
        if not event_id:
            abort(400, 'event does not exist')
        event_users = session.query(EmployerInfo).filter(EmployerInfo.event_id == event_id).all()
        event_users = list(map(lambda user: user.as_dict(), event_users))
        best_match = find_best_match(event_users, params['image'])
        return best_match if best_match and best_match['userInfo']['userId'] not in params['previousIds'] else None

    def post(self):
        params = self.post_reqparse.parse_args()
        linkedin_info = params['linkedinInfo']
        event_key = params['eventKey']

        # find matching event (validating QR code)
        event_id = None
        matched_event = session.query(Event).filter_by(event_key = event_key).first()
        if matched_event:
            event_id = matched_event.as_dict()['eventId']
        else:
            abort(400, 'No event matched this key!')

        # add a user and their photo if they don't already exist
        matching_user = session.query(Entity).filter_by(name = linkedin_info['formattedName']).first()
        user_id = None
        if matching_user is None:
            if (linkedin_info['pictureUrls'] and len(linkedin_info['pictureUrls']['values']) > 0):
                new_user = Entity(str(linkedin_info['formattedName']), str(linkedin_info['pictureUrls']['values'][0]))
                session.add(new_user)
                session.commit()
                user_id = new_user.as_dict()['userId']
            else:
                abort(400, 'No profile pictures for the authenticated user')
        else:
            user_id = matching_user.as_dict()['userId']

        # add that user's linkedin info for a specific event, if it doesn't already exist
        if session.query(EmployerInfo).filter_by(user_id = user_id, event_id = event_id).first() is None:
            summary = linkedin_info['summary'] if 'summary' in linkedin_info.keys() else 'Nothing to see here...'
            headline = linkedin_info['headline'] if 'headline' in linkedin_info.keys() else 'Talk to me to find out more!'

            email = linkedin_info['emailAddress'] if 'emailAddress' in linkedin_info.keys() else 'No email found.'
            user_info = EmployerInfo(user_id, event_id, summary, headline, linkedin_info['publicProfileUrl'], email)
            session.add(user_info)
            session.commit()

            # add positions
            if 'values' in linkedin_info['positions'].keys():
                for position in linkedin_info['positions']['values']:
                    date_start = str(position['startDate']['month']) + "/" + str(position['startDate']['year'])
                    date_end = str(position['endDate']['month']) + "/" + str(position['endDate']['year']) if 'endDate' in position.keys() else None
                    position_to_add = EmployerJob(user_info.as_dict()['employerInfoId'], position['location']['name'], position['title'], position['company']['name'], date_start, date_end, position['isCurrent'])
                    session.add(position_to_add)

        session.commit()
        return "Success!"

class EventInfo(Resource):
    def __init__(self):
        # used for auth
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('eventKey', type=str, location='json', required=True)
        self.reqparse.add_argument('name', type=str, location='json', required=True)

        self.get_reqparse = reqparse.RequestParser()
        self.get_reqparse.add_argument('eventKey', type=str, location='args', required=True)

    def get(self):
        params = self.get_reqparse.parse_args()
        event_key = params['eventKey']
        event = session.query(Event).filter_by(event_key = event_key).first()

        if event is None:
            abort(400, 'no matching event')
        else:
            return event.as_dict()
    def post(self):
        params = self.reqparse.parse_args()
        new_event = None
        if session.query(Event).filter_by(event_key = params['eventKey']).first() is None:
            new_event = Event(params['eventKey'], params['name'])
            session.add(new_event)
        else:
            abort(400, 'event already exists!')
        session.commit()
        return jsonify({"eventAdded": new_event.as_dict()})

# Define resource-based routes here
my_api.add_resource(UserInfo, '/api/userInfo', endpoint = 'info')
my_api.add_resource(EventInfo, '/api/event', endpoint = 'event')

# main server run line
if __name__ == '__main__':
    app.run(debug=True, port = port_num, host = '0.0.0.0')

