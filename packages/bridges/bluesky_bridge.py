import os
import sys
import time

from bridges.bridge_base import SCENARIO_ID, producer, ts_now
from common.geo import latlon_to_h3
from common.pol_schemas import Envelope


def meters_to_feet(meters: float) -> float:
    return meters * 3.280839895


def meters_per_second_to_knots(mps: float) -> float:
    return mps * 1.943844492


def _require_bluesky():
    try:
        import bluesky as bs  # type: ignore

        return bs
    except Exception:
        print(
            'BlueSky is required. Install into your venv: pip install "bluesky-simulator"',
            file=sys.stderr,
        )
        raise


def run_bluesky_bridge(
    scenfile: str,
    publish_hz: float = 1.0,
    dt_multiplier: float | None = None,
) -> None:
    bs = _require_bluesky()

    # Initialize a detached simulation node (no GUI, in-process)
    bs.init(mode="sim", scenfile=scenfile, detached=True)

    # Optionally speed up or slow down sim time relative to wall clock
    if dt_multiplier is not None and dt_multiplier > 0:
        bs.sim.set_dtmult(dt_multiplier)

    prod = producer()
    h3_res = int(os.getenv("H3_RES", "8"))

    # Drive the sim and publish states at the requested rate
    publish_interval = 1.0 / max(0.1, publish_hz)
    last_pub = 0.0

    # Let the scenario create/advance traffic
    while True:
        # Advance the simulation by one internal tick
        bs.sim.step()

        now = time.time()
        if now - last_pub < publish_interval:
            # Run faster than publish rate
            continue
        last_pub = now

        # Publish all aircraft states
        n = bs.traf.ntraf or 0
        if n <= 0:
            continue

        for i in range(n):
            try:
                acid = bs.traf.id[i]
                lat = float(bs.traf.lat[i])
                lon = float(bs.traf.lon[i])
                gs = float(bs.traf.gs[i])  # m/s
                trk = float(bs.traf.trk[i])  # deg
                alt_m = float(bs.traf.alt[i])  # meters
            except Exception:
                continue

            env = Envelope(
                scenario_id=SCENARIO_ID,
                source="adsb",
                ts=ts_now(),
                entity_id=str(acid),
                lat=lat,
                lon=lon,
                speed=meters_per_second_to_knots(gs),
                course=trk,
                alt=meters_to_feet(alt_m),
                attrs={"sim": "bluesky"},
                h3=latlon_to_h3(lat, lon, h3_res),
            ).model_dump()

            prod.send("adsb.raw", env)


def main() -> None:
    scen = os.getenv("BLUESKY_SCN")
    if not scen:
        print("Set BLUESKY_SCN to a .scn file path.", file=sys.stderr)
        sys.exit(2)

    try:
        hz = float(os.getenv("BLUESKY_PUBLISH_HZ", "1.0"))
    except ValueError:
        hz = 1.0

    try:
        mult_env = os.getenv("BLUESKY_DT_MULT")
        mult = float(mult_env) if mult_env else None
    except ValueError:
        mult = None

    run_bluesky_bridge(scen, publish_hz=hz, dt_multiplier=mult)


if __name__ == "__main__":
    main()
