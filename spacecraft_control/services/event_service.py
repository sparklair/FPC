"""Short-lived SQLAlchemy sessions; snapshots are serialized before commit."""
from sqlalchemy import JSON, Float, Integer, String, create_engine, event, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from ..telemetry.generator import utc_now


class Base(DeclarativeBase):
    """Declarative base for the durable mission journal."""


class JournalEntry(Base):
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    subsystem: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), index=True)
    opened_at: Mapped[str] = mapped_column(String(40))
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Alarm(Base):
    __tablename__ = "alarms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    parameter: Mapped[str] = mapped_column(String(60))
    subsystem: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    measured_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[str] = mapped_column(String(40))
    cleared_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


def serialize(model):
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


class EventStore:
    def __init__(self, url):
        options = {"connect_args": {"check_same_thread": False, "timeout": 15}}
        if url.endswith(":memory:"):
            options["poolclass"] = StaticPool
        self.engine = create_engine(url, **options)

        @event.listens_for(self.engine, "connect")
        def sqlite_pragmas(connection, _record):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        # A new process starts a new simulation; old unresolved rows stay auditable.
        with self.sessions.begin() as session:
            session.execute(update(Incident).where(Incident.status == "OPEN").values(status="INTERRUPTED", closed_at=utc_now()))
            session.execute(update(Alarm).where(Alarm.status == "ACTIVE").values(status="CLEARED", cleared_at=utc_now()))

    def append(self, kind, run_id, data, incident_id=None):
        with self.sessions.begin() as session:
            row = JournalEntry(kind=kind, timestamp=utc_now(), run_id=run_id, data=data, incident_id=incident_id)
            session.add(row)
            session.flush()
            return self._entry(row)

    @staticmethod
    def _entry(row):
        return {**row.data, "id": row.id, "timestamp": row.timestamp, "run_id": row.run_id, "incident_id": row.incident_id}

    def entries(self, kind, limit=100, before=None, incident_id=None):
        query = select(JournalEntry).where(JournalEntry.kind == kind)
        if before is not None:
            query = query.where(JournalEntry.id < before)
        if incident_id is not None:
            query = query.where(JournalEntry.incident_id == incident_id)
        with self.sessions() as session:
            return [self._entry(row) for row in session.scalars(query.order_by(JournalEntry.id.desc()).limit(limit))]

    def open_incident(self, run_id, subsystem, title):
        with self.sessions.begin() as session:
            row = Incident(run_id=run_id, subsystem=subsystem, title=title, status="OPEN", opened_at=utc_now())
            session.add(row)
            session.flush()
            return row.id

    def close_incident(self, incident_id, status="RESOLVED"):
        with self.sessions.begin() as session:
            session.execute(update(Incident).where(Incident.id == incident_id).values(status=status, closed_at=utc_now()))

    def incidents(self, limit=30):
        with self.sessions() as session:
            return [serialize(row) for row in session.scalars(select(Incident).order_by(Incident.id.desc()).limit(limit))]

    def alarm_transition(self, run_id, rule, severity, value, incident_id, alarm_id=None):
        with self.sessions.begin() as session:
            row = session.get(Alarm, alarm_id) if alarm_id else Alarm(
                run_id=run_id, parameter=rule.parameter, subsystem=rule.subsystem, opened_at=utc_now(),
            )
            row.severity = severity
            row.status = "CLEARED" if severity == "NORMAL" else "ACTIVE"
            row.measured_value = value
            row.threshold = rule.threshold(severity)
            row.incident_id = incident_id
            if severity == "NORMAL":
                row.cleared_at = utc_now()
            session.add(row)
            session.flush()
            return row.id

    def alarm_history(self, limit=100):
        with self.sessions() as session:
            return [serialize(row) for row in session.scalars(select(Alarm).order_by(Alarm.id.desc()).limit(limit))]
