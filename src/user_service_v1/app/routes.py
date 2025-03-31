
"""
This module defines the routes for user-related operations in a Flask application using Flask-RESTx.
It includes endpoints for creating, updating, and retrieving user information, with validation and error handling.
Classes:
    UserList(Resource): Handles creating new users (POST) and retrieving all users (GET).
    User(Resource): Handles retrieving a single user (GET) and updating an existing user (PUT).
Routes:
    /users/ (GET): Retrieves all users.
    /users/ (POST): Creates a new user.
    /users/<string:id> (GET): Retrieves an existing user by userId.
    /users/<string:id> (PUT): Updates an existing user.
Note:
    This is v1, but with automatic timestamps similar to v2.
"""
import uuid
from datetime import datetime
from bson.objectid import ObjectId
from flask import request, Flask, current_app
from flask_restx import Namespace, Resource, fields
from user_service_v1.app.models import api, user_model
from user_service_v1.app.events import publish_user_update_event
# current_app is a proxy to the Flask application handling the request.
current_app: Flask
@api.route('/')
class UserList(Resource):
    """
    Handles:
      - GET: retrieve all users
      - POST: create a new user
    """
    @api.marshal_list_with(user_model, code=200)
    def get(self):
        """
        Retrieve all users from the database.
        
        Returns:
            list[dict]: A list of all user documents.
        """
        users_collection = current_app.users_collection
        all_users = list(users_collection.find())
        return all_users, 200
    @api.expect(user_model)
    @api.marshal_with(user_model, code=201)
    def post(self) -> tuple:
        """
        Create a new user.
        
        Steps:
        1. Parse JSON data.
        2. Validate fields (emails, deliveryAddress, etc.).
        3. Check if emails already exist.
        4. Generate userId.
        5. Insert user with automatic timestamps (createdAt, updatedAt).
        6. Return the newly created user.
        """
        try:
            data: dict = request.json
        except Exception as e:
            api.abort(400, f'Invalid JSON data: {str(e)}')
        allowed_fields = {
            'emails', 'deliveryAddress', 'firstName', 'lastName',
            'phoneNumber', 'createdAt', 'updatedAt'
        }
        for field in data:
            if field not in allowed_fields:
                api.abort(400, f'Invalid field: {field}')
        if 'emails' not in data or not data['emails']:
            api.abort(400, 'emails is a required field')
        if 'deliveryAddress' not in data:
            api.abort(400, 'deliveryAddress is a required field')
        # Validate deliveryAddress
        delivery_address = data['deliveryAddress']
        required_fields = ['street', 'city', 'state', 'postalCode', 'country']
        if not isinstance(delivery_address, dict):
            api.abort(400, 'deliveryAddress must be an object')
        for field in required_fields:
            if field not in delivery_address or not isinstance(delivery_address[field], str):
                api.abort(400, f'deliveryAddress must contain a valid {field}')
        users_collection = current_app.users_collection
        # Check if any of the emails already exist
        existing_user = users_collection.find_one({'emails': {'$in': data['emails']}})
        if existing_user:
            api.abort(400, 'One or more email addresses are already in use')
        # Generate a unique userId
        data['userId'] = str(uuid.uuid4())
        # Automatically set createdAt and updatedAt
        current_time = datetime.utcnow()
        data['createdAt'] = current_time
        data['updatedAt'] = current_time
        user_id = users_collection.insert_one(data).inserted_id
        new_user = users_collection.find_one({'_id': ObjectId(user_id)})
        return new_user, 201

@api.route('/<string:id>')
@api.response(404, 'User not found')
class User(Resource):
    """
    Handles:
      - GET: retrieve a single user by userId
      - PUT: update an existing user
    """
    @api.marshal_with(user_model)
    def get(self, id: str):
        """
        Retrieve a user by userId.
        
        Args:
            id (str): The unique identifier of the user.
        Returns:
            dict: The user document if found.
        Raises:
            404: If the user is not found.
        """
        users_collection = current_app.users_collection
        user = users_collection.find_one({'userId': id})
        if not user:
            api.abort(404, "User not found")
        return user
    @api.expect(user_model)
    @api.marshal_with(user_model)
    def put(self, id: str) -> list:
        """
        Update user information based on the provided user ID.
        Automatically updates the 'updatedAt' field.
        
        Returns:
            list: [old_user, new_user]
        """
        try:
            data: dict = request.json
        except Exception as e:
            api.abort(400, f'Invalid JSON data: {str(e)}')
        allowed_fields = {'emails', 'deliveryAddress'}
        for field in data:
            if field not in allowed_fields:
                api.abort(400, f'Invalid field: {field}')
        if 'emails' not in data and 'deliveryAddress' not in data:
            api.abort(400, 'Either emails or deliveryAddress is required')
        # Validate emails
        if 'emails' in data:
            if not isinstance(data['emails'], list) or not all(
                isinstance(email, str) and '@' in email for email in data['emails']
            ):
                api.abort(400, 'emails must be a list of valid email addresses')
        # Validate deliveryAddress
        if 'deliveryAddress' in data:
            delivery_address = data['deliveryAddress']
            required_fields = ['street', 'city', 'state', 'postalCode', 'country']
            if not isinstance(delivery_address, dict):
                api.abort(400, 'deliveryAddress must be an object')
            for field in required_fields:
                if field not in delivery_address or not isinstance(delivery_address[field], str):
                    api.abort(400, f'deliveryAddress must contain a valid {field}')
        users_collection = current_app.users_collection
        old_user = users_collection.find_one({'userId': id})
        if not old_user:
            api.abort(404, "User not found")
        # Automatically update updatedAt
        data['updatedAt'] = datetime.utcnow()
        users_collection.update_one({'userId': id}, {'$set': data})
        new_user = users_collection.find_one({'userId': id})
        # Publish update event so the Order service can sync
        emails = new_user.get("emails", [])
        delivery_address = new_user.get("deliveryAddress", {})
        publish_user_update_event(id, emails, delivery_address)
        return [old_user, new_user]