import os
import csv
import math
import requests
from flask import Flask, request, jsonify
from opensky_api import OpenSkyApi

app = Flask(__name__)

# --- 1) Load your visual‐ID database (from the CSV you uploaded) ---
AIRCRAFT_DB = []
with open('Aircraft_Complete_Data.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        AIRCRAFT_DB.append(row)

# --- 2) AviationStack configuration (for /flight and /nearbyairports) ---
AVIATIONSTACK_KEY = os.environ.get('AVIATIONSTACK_KEY', '4749f77fac737f1c613ea58453473d67')
FLIGHTS_API_URL   = 'http://api.aviationstack.com/v1/flights'
AIRPORTS_API_URL  = 'http://api.aviationstack.com/v1/airports'

# --- Utility: Haversine distance in km ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# --- /around: list aircraft within ~30 km of your lat/lon ---
@app.route('/around', methods=['GET'])
def around():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'Please provide lat and lon parameters.'}), 400

    # build a ~30 km square around (lat,lon)
    buffer_deg = 30.0 / 111.0
    lamin, lamax = lat - buffer_deg, lat + buffer_deg
    lomin, lomax = lon - buffer_deg, lon + buffer_deg

    api = OpenSkyApi()
    states = api.get_states(bbox=(lamin, lamax, lomin, lomax))

    flights = []
    if states and states.states:
        for s in states.states:
            if s.latitude is None or s.longitude is None:
                continue
            dist = haversine(lat, lon, s.latitude, s.longitude)
            flights.append({
                'callsign':    s.callsign,
                'icao24':      s.icao24,
                'origin_country': s.origin_country,
                'latitude':      s.latitude,
                'longitude':     s.longitude,
                'altitude_m':    s.geo_altitude,
                'speed_m_s':     s.velocity,
                'distance_km':   round(dist, 2)
            })

    return jsonify({'flights': flights})

# --- /identify: match visual description to aircraft model ---
@app.route('/identify', methods=['GET'])
def identify():
    desc = request.args.get('desc', '').lower()
    if not desc:
        return jsonify({'error': 'Please provide desc parameter describing the aircraft.'}), 400

    scores = []
    for row in AIRCRAFT_DB:
        clues = ' '.join([
            row['Engine Type & Number'],
            row['Tail Configuration'],
            row['Wing Configuration'],
            row['Distinctive Visual Features']
        ]).lower()
        # count how many clue‐words appear in the description
        cnt = sum(1 for phrase in clues.split() if phrase and phrase in desc)
        scores.append((cnt, row['Aircraft Model']))

    scores.sort(key=lambda x: -x[0])
    matches = [model for cnt, model in scores if cnt > 0]
    if not matches:
        return jsonify({'matches': [], 'message': 'No matching aircraft found.'})

    return jsonify({'matches': matches[:3]})

# --- /flight: lookup by flight number via AviationStack ---
@app.route('/flight', methods=['GET'])
def flight_lookup():
    fn = request.args.get('flight_number', '').upper()
    if not fn:
        return jsonify({'error': 'Please provide flight_number parameter.'}), 400
    if not AVIATIONSTACK_KEY:
        return jsonify({'error': 'AVIATIONSTACK_KEY is not set.'}), 500

    params = {'access_key': AVIATIONSTACK_KEY, 'flight_iata': fn}
    resp = requests.get(FLIGHTS_API_URL, params=params, timeout=10)
    data = resp.json().get('data', [])
    return jsonify({'flights': data})

# --- /nearbyairports: list airports near given lat/lon via AviationStack ---
@app.route('/nearbyairports', methods=['GET'])
def nearby_airports():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'Please provide lat and lon parameters.'}), 400
    if not AVIATIONSTACK_KEY:
        return jsonify({'error': 'AVIATIONSTACK_KEY is not set.'}), 500

    params = {
        'access_key': AVIATIONSTACK_KEY,
        'lat':        lat,
        'lon':        lon,
        'distance':   50  # km
    }
    resp = requests.get(AIRPORTS_API_URL, params=params, timeout=10)
    data = resp.json().get('data', [])
    return jsonify({'airports': data})

# --- /nextoverhead: find the single closest aircraft ---
@app.route('/nextoverhead', methods=['GET'])
def next_overhead():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'Please provide lat and lon parameters.'}), 400

    # same 30 km box
    buffer_deg = 30.0 / 111.0
    lamin, lamax = lat - buffer_deg, lat + buffer_deg
    lomin, lomax = lon - buffer_deg, lon + buffer_deg

    api = OpenSkyApi()
    states = api.get_states(bbox=(lamin, lamax, lomin, lomax))

    candidates = []
    if states and states.states:
        for s in states.states:
            if s.latitude is None or s.longitude is None:
                continue
            dist = haversine(lat, lon, s.latitude, s.longitude)
            candidates.append((dist, s))

    if not candidates:
        return jsonify({'message': 'No aircraft found nearby.'})

    candidates.sort(key=lambda x: x[0])
    closest = candidates[0][1]
    return jsonify({
        'next_overhead': {
            'callsign':    closest.callsign,
            'icao24':      closest.icao24,
            'distance_km': round(candidates[0][0], 2)
        }
    })

# --- /aircraftinfo: return full row from your visual DB ---
@app.route('/aircraftinfo', methods=['GET'])
def aircraft_info():
    typ = request.args.get('type', '').lower()
    if not typ:
        return jsonify({'error': 'Please provide type parameter (aircraft model name).'}), 400

    for row in AIRCRAFT_DB:
        if row['Aircraft Model'].lower() == typ:
            return jsonify({'info': row})

    return jsonify({'message': 'Specified aircraft model not found.'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
