"""
_summary_
This module defines the routes for order-related operations in a Flask application 
using Flask-RESTx. It includes endpoints for creating, retrieving, and updating 
orders, with validation and error handling.

Classes:
    OrderList(Resource): Handles the creation of new orders and retrieval of orders 
                         by status.
    OrderStatus(Resource): Handles the updating of order status.
    OrderDetails(Resource): Handles the updating of order emails or delivery address.
Routes:
    /orders/ (POST): Creates a new order.
    /orders/ (GET): Retrieves orders by status.
    /orders/<string:id>/status (PUT): Updates the status of an existing order.
    /orders/<string:id>/details (PUT): Updates the emails or delivery address of 
                                       an existing order.
Author:
    @TheBarzani
"""

import uuid
from datetime import datetime
from flask import request, Flask, current_app
from flask_restx import Resource, fields
from bson.objectid import ObjectId
from order_service.app.models import api, order_model, delivery_address_model

# The current_app variable is a proxy to the Flask application handling the request.
current_app: Flask

@api.route('/')
class OrderList(Resource):
    """Resource for handling creation of orders and retrieval of orders by status."""

    @api.expect(order_model)
    @api.marshal_with(order_model, code=201)
    def post(self) -> tuple:
        """
        Handles the HTTP POST request to create a new order.
        Performs the following:
            - Parses JSON data.
            - Validates required fields.
            - Validates the structure of 'items' and 'deliveryAddress'.
            - Adds automatic timestamps.
            - Generates a unique orderId.
            - Inserts the new order into the database.
        Returns:
            tuple: The newly created order data and HTTP status code 201.
        """
        data: dict = request.json

        # Ensure no additional fields are present
        allowed_fields: set = {'items', 'userEmails', 'deliveryAddress', 'orderStatus',
                               'createdAt', 'updatedAt', 'userId'}
        for field in data:
            if field not in allowed_fields:
                api.abort(400, f'Invalid field: {field}')

        if 'items' not in data or not data['items']:
            api.abort(400, 'items is a required field')
        if 'userEmails' not in data or not data['userEmails']:
            api.abort(400, 'userEmails is a required field')
        if 'deliveryAddress' not in data:
            api.abort(400, 'deliveryAddress is a required field')
        if 'orderStatus' not in data:
            api.abort(400, 'orderStatus is a required field')

        # Validate items
        for item in data['items']:
            if not isinstance(item, dict):
                api.abort(400, 'Each item must be an object')
            required_fields: list = ['itemId', 'quantity', 'price']
            for field in required_fields:
                if field not in item or not isinstance(item[field], (str, int, float)):
                    api.abort(400, f'Each item must contain a valid {field}')

        # Validate deliveryAddress
        delivery_address: dict = data['deliveryAddress']
        required_addr_fields: list = ['street', 'city', 'state', 'postalCode', 'country']
        if not isinstance(delivery_address, dict):
            api.abort(400, 'deliveryAddress must be an object')
        for field in required_addr_fields:
            if field not in delivery_address or not isinstance(delivery_address[field], str):
                api.abort(400, f'deliveryAddress must contain a valid {field}')

        orders_collection = current_app.orders_collection

        # Add automatic timestamps
        current_time = datetime.utcnow()
        data['createdAt'] = current_time
        data['updatedAt'] = current_time

        # Generate a unique orderId
        data['orderId'] = str(uuid.uuid1())
        order_id: ObjectId = orders_collection.insert_one(data).inserted_id
        order: dict = orders_collection.find_one({'_id': ObjectId(order_id)})
        return order, 201

    @api.param('status', 'The status of the orders to retrieve')
    @api.marshal_with(order_model, as_list=True)
    def get(self) -> list:
        """
        Retrieves orders by status.
        Expects a query parameter 'status' with one of:
        'under process', 'shipping', or 'delivered'.
        """
        status: str = request.args.get('status')
        if not status or status not in ['under process', 'shipping', 'delivered']:
            api.abort(400, 'Invalid or missing status parameter')

        orders_collection = current_app.orders_collection
        orders: list = list(orders_collection.find({'orderStatus': status}))
        return orders

@api.route('/<string:id>/status')
@api.response(404, 'Order not found')
class OrderStatus(Resource):
    """Resource for updating the status of an order."""

    @api.expect(api.model('OrderStatus', {
        'orderStatus': fields.String(required=True, description='Current status of the order', 
                                     enum=['under process', 'shipping', 'delivered'])
    }))
    @api.marshal_with(order_model)
    def put(self, id: str) -> dict:
        """
        Updates the status of an existing order.
        Also updates the 'updatedAt' timestamp.
        """
        data: dict = request.json

        if 'orderStatus' not in data or data['orderStatus'] not in ['under process', 'shipping', 'delivered']:
            api.abort(400, 'Invalid or missing orderStatus')

        orders_collection = current_app.orders_collection
        old_order: dict = orders_collection.find_one({'orderId': id})
        if not old_order:
            api.abort(404, "Order not found")

        # Update orderStatus and set updatedAt automatically
        updated_data = {
            'orderStatus': data['orderStatus'],
            'updatedAt': datetime.utcnow()
        }
        orders_collection.update_one({'orderId': id}, {'$set': updated_data})
        new_order: dict = orders_collection.find_one({'orderId': id})

        return [old_order, new_order]

@api.route('/<string:id>/details')
@api.response(404, 'Order not found')
class OrderDetails(Resource):
    """Resource for updating order emails or delivery address."""

    @api.expect(api.model('OrderDetails', {
        'userEmails': fields.List(fields.String, description='List of email addresses associated with the order'),
        'deliveryAddress': fields.Nested(delivery_address_model, description='The delivery address of the user')
    }))
    @api.marshal_with(order_model)
    def put(self, id: str) -> dict:
        """
        Updates the emails or delivery address of an existing order.
        Also updates the 'updatedAt' timestamp.
        """
        data: dict = request.json

        # Ensure no other fields are present
        allowed_fields: set = {'userEmails', 'deliveryAddress'}
        for field in data:
            if field not in allowed_fields:
                api.abort(400, f'Invalid field: {field}')

        if 'userEmails' not in data and 'deliveryAddress' not in data:
            api.abort(400, 'Either userEmails or deliveryAddress is required')

        # Validate userEmails
        if 'userEmails' in data:
            if not isinstance(data['userEmails'], list) or not all(isinstance(email, str) and '@' in email for email in data['userEmails']):
                api.abort(400, 'userEmails must be an array of valid email addresses')

        # Validate deliveryAddress
        if 'deliveryAddress' in data:
            delivery_address: dict = data['deliveryAddress']
            required_addr_fields: list = ['street', 'city', 'state', 'postalCode', 'country']
            if not isinstance(delivery_address, dict):
                api.abort(400, 'deliveryAddress must be an object')
            for field in required_addr_fields:
                if field not in delivery_address or not isinstance(delivery_address[field], str):
                    api.abort(400, f'deliveryAddress must contain a valid {field}')

        orders_collection = current_app.orders_collection
        old_order: dict = orders_collection.find_one({'orderId': id})
        if not old_order:
            api.abort(404, "Order not found")

        # Set updatedAt automatically
        data['updatedAt'] = datetime.utcnow()

        orders_collection.update_one({'orderId': id}, {'$set': data})
        new_order: dict = orders_collection.find_one({'orderId': id})

        return [old_order, new_order]
