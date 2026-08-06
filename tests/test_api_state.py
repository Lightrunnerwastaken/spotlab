import json
import math

from spotlab.api.state import as_sample, from_proto
from spotlab.backends.dryrun import DryRunBackend


def test_zustand_aus_protobuf():
    backend = DryRunBackend()
    backend.power_on()
    zustand = from_proto(backend.robot_state())
    assert zustand.battery == 87.0
    assert zustand.powered is True
    assert len(zustand.joints) == 12
    assert zustand.joints["fl.hx"].position == 0.0
    assert zustand.feet == (True, True, True, True)


def test_pose_aus_identitaet_ist_ursprung():
    zustand = from_proto(DryRunBackend().robot_state())
    x, y, yaw = zustand.pose
    assert (x, y) == (0.0, 0.0)
    assert math.isclose(yaw, 0.0, abs_tol=1e-9)


def test_abtastung_ist_flach_und_json_faehig():
    probe = as_sample(DryRunBackend().robot_state())
    json.dumps(probe)  # darf nicht werfen
    assert probe["battery"] == 87.0
    assert probe["pose"] == [0.0, 0.0, 0.0]
    assert probe["joints"]["fl.hy"]["position"] == 0.0
    assert probe["feet"] == [True, True, True, True]
