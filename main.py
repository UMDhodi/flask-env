from flask import Flask, jsonify, request
import pandas as pd
import json
import math
from mysql.connector import connection
from flask_cors import CORS  # Import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000/"}})  # Enable CORS for all origins and /api/* routes

# Define AWS Credentials
DB_HOST = 'awsdatabase.cvmkooke0uh1.us-east-1.rds.amazonaws.com'
DB_PORT = '3306'
DB_USER = 'admin'
DB_PASSWORD = 'tu13dekh'
DB_NAME = 'aws'

# Average speeds for transport modes in km/h
TRANSPORT_SPEEDS = {
    "Truck": 60,
    "Plane": 900
}

# Constants for carbon emission calculations
EMISSION_FACTOR_CAR_URBAN = 0.12

# Function to connect to AWS RDS database
def connect_to_rds():
    try:
        conn = connection.MySQLConnection(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except Exception as e:
        print(f"Error connecting to AWS RDS: {e}")
        return None

# Function to calculate distance using the Haversine formula
def calculate_distance(lon1, lat1, lon2, lat2):
    R = 6371.0
    lon1_rad = math.radians(lon1)
    lat1_rad = math.radians(lat1)
    lon2_rad = math.radians(lon2)
    lat2_rad = math.radians(lat2)
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  # distance in km

# Function to calculate adjusted distance and carbon emission
def calculate_carbon_emission(lon1, lat1, lon2, lat2):
    point_to_point_distance = calculate_distance(lon1, lat1, lon2, lat2)
    adjusted_distance = point_to_point_distance * 1.2
    carbon_emission = adjusted_distance * EMISSION_FACTOR_CAR_URBAN
    return {
        "Point-to-point distance (km)": point_to_point_distance,
        "Adjusted distance (km)": adjusted_distance,
        "Carbon emission (kg CO2)": carbon_emission
    }

# Function to fetch package data from the database
def get_package_details(package_id, conn):
    query = f"SELECT Weight, TransportMode, DepartureLon, DepartureLat, ArrivalLon, ArrivalLat FROM aws.TransportData WHERE ID = %s"
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, (package_id,))
    result = cursor.fetchone()
    cursor.close()
    return result

# Function to calculate estimated delivery days
def calculate_estimated_delivery_days(transport_mode, adjusted_distance):
    speed = TRANSPORT_SPEEDS.get(transport_mode, None)
    if not speed:
        return "Transport mode not recognized"
    travel_times_hours = adjusted_distance / speed
    if transport_mode.lower() == "Truck":
        delay = 0.5
    elif transport_mode.lower() == "Plane":
        delay = 1
    else:
        delay = 1

    delivery_days = (travel_times_hours / 24) + delay
    return math.ceil(delivery_days)  # Round up to the nearest whole day

# API route to calculate delivery data
@app.route('/api/delivery/<package_id>', methods=['GET'])
def get_delivery_data(package_id):
    conn = connect_to_rds()
    if not conn:
        return jsonify({"error": "Unable to connect to the database"}), 500

    package_details = get_package_details(package_id, conn)

    if not package_details:
        return jsonify({"error": "Package ID not found"}), 404

    departure_lon, departure_lat = package_details['DepartureLon'], package_details['DepartureLat']
    arrival_lon, arrival_lat = package_details['ArrivalLon'], package_details['ArrivalLat']
    transport_mode = package_details['TransportMode']
    weight = package_details['Weight']

    # Calculate carbon emission and delivery days
    emission_data = calculate_carbon_emission(departure_lon, departure_lat, arrival_lon, arrival_lat)
    adjusted_distance = emission_data["Adjusted distance (km)"]
    delivery_days = calculate_estimated_delivery_days(transport_mode, adjusted_distance)

    # Prepare the response data
    response = {
        "Package ID": package_id,
        "Weight": weight,
        "Estimated delivery days": delivery_days,
        "Transport Mode": transport_mode,
        "Point-to-point distance (km)": emission_data["Point-to-point distance (km)"],
        "Adjusted distance (km)": emission_data["Adjusted distance (km)"],
        "Carbon emission (kg CO2)": emission_data["Carbon emission (kg CO2)"]
    }

    conn.close()
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
