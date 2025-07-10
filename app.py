from flask import Flask, request, jsonify
from opensky_api import OpenSkyApi
import time

app = Flask(__name__)

@app.route('/get_flights', methods=['GET'])
def get_flights():
    try:
        lamin = float(request.args.get('lamin'))
        lamax = float(request.args.get('lamax'))
        lomin = float(request.args.get('lomin'))
        lomax = float(request.args.get('lomax'))

        api = OpenSkyApi()
        states = api.get_states(bbox=(lamin, lamax, lomin, lomax))

        flights = []
        if states and states.states:
            for s in states.states:
                flights.append({
                    'callsign': s.callsign,
                    'icao24': s.icao24,
                    'origin_country': s.origin_country,
                    'latitude': s.latitude,
                    'longitude': s.longitude,
                    'altitude': s.baro_altitude,
                    'speed': s.velocity
                })

        return jsonify({'flights': flights})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
