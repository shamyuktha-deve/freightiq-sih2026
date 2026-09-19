from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Boolean, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Port(Base):
    __tablename__ = "ports"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    country = Column(String(50), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    terminal_name = Column(String(150), nullable=False)

    constraints = relationship("PortConstraint", back_populates="port", cascade="all, delete-orphan")
    routes = relationship("Route", back_populates="destination_port")
    recommendations = relationship("CharterRecommendation", back_populates="port")

class PortConstraint(Base):
    __tablename__ = "port_constraints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    port_id = Column(String(50), ForeignKey("ports.id"), nullable=False, index=True)
    max_loa = Column(Float, nullable=False)
    max_beam = Column(Float, nullable=False)
    max_draft_cd = Column(Float, nullable=False)
    air_draft_limit = Column(Float, nullable=True)
    min_ukc_pct = Column(Float, default=10.0)
    daily_discharge_rate_tpd = Column(Integer, nullable=True)
    advisory_notice = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    port = relationship("Port", back_populates="constraints")

class Route(Base):
    __tablename__ = "routes"

    id = Column(String(50), primary_key=True, index=True)
    origin_port = Column(String(100), nullable=False)
    origin_country = Column(String(50), nullable=False)
    destination_port_id = Column(String(50), ForeignKey("ports.id"), nullable=False)
    primary_cargo = Column(String(100), nullable=False)
    typical_vessel_class = Column(String(50), nullable=False)
    distance_nautical_miles = Column(Integer, nullable=True)
    average_transit_days = Column(Float, nullable=True)

    destination_port = relationship("Port", back_populates="routes")
    freight_rates = relationship("FreightRate", back_populates="route", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="route", cascade="all, delete-orphan")
    recommendations = relationship("CharterRecommendation", back_populates="route")

class Vessel(Base):
    __tablename__ = "vessels"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    vessel_class = Column(String(50), nullable=False, index=True)
    dwt = Column(Integer, nullable=False)
    loa = Column(Float, nullable=False)
    beam = Column(Float, nullable=False)
    design_draft = Column(Float, nullable=False)
    daily_demurrage_rate = Column(Float, default=22500.00)

    recommendations = relationship("CharterRecommendation", back_populates="vessel")

class FreightRate(Base):
    __tablename__ = "freight_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String(50), ForeignKey("routes.id"), nullable=False, index=True)
    rate_date = Column(Date, nullable=False, index=True)
    spot_rate = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    unit = Column(String(10), default="MT")
    data_source = Column(String(100), nullable=False)
    is_simulated = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("route_id", "rate_date", name="uq_route_rate_date"),
    )

    route = relationship("Route", back_populates="freight_rates")

class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String(50), ForeignKey("routes.id"), nullable=False, index=True)
    forecast_generated_at = Column(DateTime, default=datetime.utcnow)
    target_date = Column(Date, nullable=False, index=True)
    horizon_days = Column(Integer, nullable=False)
    predicted_rate = Column(Float, nullable=False)
    ci_lower_80 = Column(Float, nullable=False)
    ci_upper_80 = Column(Float, nullable=False)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(20), nullable=False)
    is_simulated = Column(Boolean, default=True)

    route = relationship("Route", back_populates="forecasts")

class CharterRecommendation(Base):
    __tablename__ = "charter_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(String(50), ForeignKey("routes.id"), nullable=False)
    vessel_id = Column(String(50), ForeignKey("vessels.id"), nullable=False)
    port_id = Column(String(50), ForeignKey("ports.id"), nullable=False)
    recommended_action = Column(String(50), nullable=False)
    when_window = Column(String(100), nullable=False)
    feasibility_verdict = Column(String(50), nullable=False)
    expected_savings_usd = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=False)
    reasoning_summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    route = relationship("Route", back_populates="recommendations")
    vessel = relationship("Vessel", back_populates="recommendations")
    port = relationship("Port", back_populates="recommendations")

class DataSourceMetadata(Base):
    __tablename__ = "data_sources_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(150), nullable=False)
    collection_date = Column(Date, nullable=True)
    confidence_rating = Column(String(50), nullable=True)
    update_cadence = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    is_simulated = Column(Boolean, default=True)
