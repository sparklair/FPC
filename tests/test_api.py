import pytest


@pytest.mark.parametrize("endpoint", ["/", "/api/telemetry/current", "/api/telemetry/history", "/api/events", "/api/alarms", "/api/alarms?history=true", "/api/commands", "/api/status", "/api/snapshot", "/api/incidents"])
def test_endpoints(client, endpoint):
    assert client.get(endpoint).status_code == 200


@pytest.mark.parametrize("endpoint,data", [
    ("/api/command", {}), ("/api/command", {"command":"DESTROY"}),
    ("/api/command", {"command":[]}), ("/api/command", []),
    ("/api/fault/inject", {"fault":"UNKNOWN"}), ("/api/fault/inject", {"fault":{}}),
    ("/api/simulation", {"action":"speed","value":True}),
    ("/api/simulation", {"action":"speed","value":100}),
    ("/api/simulation", {"action":"speed","value":"2"}),
    ("/api/simulation", {"action":"demo","value":"false"}),
    ("/api/simulation", {"action":[]}),
])
def test_invalid_inputs_are_400(client, endpoint, data):
    response = client.post(endpoint,json=data)
    assert response.status_code == 400
    assert "error" in response.json


@pytest.mark.parametrize("query", ["limit=0", "limit=999999", "limit=abc", "before=-1", "before=no"])
def test_invalid_pagination(client, query):
    assert client.get('/api/events?'+query).status_code == 400


def test_malformed_and_oversized_requests(client):
    assert client.post('/api/command',data='broken',content_type='application/json').status_code == 400
    assert client.post('/api/command',json={'command':'x'*5000}).status_code == 413


def test_command_conflict_recorded(client, mission):
    assert client.post('/api/command',json={'command':'ENTER_SAFE_MODE'}).status_code == 200
    assert client.post('/api/command',json={'command':'PAYLOAD_ON'}).status_code == 409
    assert mission.store.entries('command')[0]['result'] == 'REJECTED'


def test_fault_api_and_reset(client, mission):
    assert client.post('/api/fault/inject',json={'fault':'BATTERY_DRAIN'}).status_code == 200
    assert client.post('/api/fault/inject',json={'fault':'BATTERY_DRAIN'}).status_code == 400
    assert 'BATTERY_DRAIN' in mission.current['faults']
    assert client.post('/api/fault/reset').status_code == 200
    assert not mission.current['faults']


def test_socket_stream_reconnect_and_reset(app, mission):
    socketio = app.extensions['socketio']
    first = socketio.test_client(app)
    initial = first.get_received()
    assert initial[0]['name'] == 'initial_state'
    mission.tick()
    assert {'telemetry_update','alarm_update','spacecraft_status_update','incident_update'} <= {message['name'] for message in first.get_received()}
    first.disconnect()
    mission.inject_fault('PAYLOAD_OVERHEAT')
    for _ in range(30):
        mission.tick()
    second = socketio.test_client(app)
    snapshot = second.get_received()[0]['args'][0]
    assert snapshot['telemetry']['telemetry_sequence_number'] == 31
    assert snapshot['commands']
    assert len(snapshot['history']) == 32
    mission.operator_command('COMMS_REACQUIRE')
    names = {message['name'] for message in second.get_received()}
    assert {'command_update','event_update'} <= names
    mission.reset()
    assert 'simulation_reset' in {message['name'] for message in second.get_received()}
    second.disconnect()


def test_journal_pagination(client, mission):
    for _ in range(10):
        mission.operator_command('PAYLOAD_OFF')
    first = client.get('/api/commands?limit=3').json
    second = client.get('/api/commands',query_string={'limit':3,'before':first[-1]['id']}).json
    assert len(first) == len(second) == 3
    assert {row['id'] for row in first}.isdisjoint({row['id'] for row in second})
