from common.pol_schemas import Envelope
from normalizers.db_writer import TracksWriter
from normalizers.norm_base import make_consumer, make_producer

IN_TOPIC, OUT_TOPIC = "adsb.raw", "adsb.norm"


def main():
    c = make_consumer(IN_TOPIC)
    p = make_producer()
    writer = TracksWriter(table="tracks_adsb")
    for msg in c:
        env = Envelope(**msg.value)
        p.send(OUT_TOPIC, env.model_dump())
        writer.write_envelope(env)


if __name__ == "__main__":
    main()
