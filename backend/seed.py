import os
import sys
from datetime import datetime, timedelta, date

# Add parent directory to path so app modules import cleanly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, SessionLocal, Base
from app.models.models import (
    Port,
    PortConstraint,
    Route,
    Vessel,
    FreightRate,
    DataSourceMetadata,
)

def seed_database():
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(Port).first():
            print("Database already contains records. Purging for clean re-seed...")
            db.query(FreightRate).delete()
            db.query(Route).delete()
            db.query(PortConstraint).delete()
            db.query(Port).delete()
            db.query(Vessel).delete()
            db.query(DataSourceMetadata).delete()
            db.commit()

        # 1. Ports
        ports_data = [
            Port(
                id="paradip",
                name="Paradip Port",
                country="India",
                latitude=20.2644,
                longitude=86.6719,
                terminal_name="Mechanized Coal Berth (MCHW)"
            ),
            Port(
                id="vizag",
                name="Visakhapatnam Port",
                country="India",
                latitude=17.6980,
                longitude=83.2980,
                terminal_name="Outer Harbour Coal Terminal (EQ-1)"
            ),
            Port(
                id="dhamra",
                name="Dhamra Port",
                country="India",
                latitude=20.8167,
                longitude=86.9667,
                terminal_name="Deep Draft Berth 1 (Capesize Iron/Coal)"
            ),
        ]
        db.add_all(ports_data)
        db.commit()
        print(f"Seeded {len(ports_data)} ports.")

        # 2. Port Constraints
        constraints_data = [
            PortConstraint(
                port_id="paradip",
                max_loa=300.0,
                max_beam=48.0,
                max_draft_cd=14.5,
                air_draft_limit=22.0,
                min_ukc_pct=10.0,
                daily_discharge_rate_tpd=45000,
                advisory_notice=(
                    "Harbour Master Advisory: Night navigation allowed up to LOA 260m. "
                    "Vessels > 280m require 2 escort tugs during flood tide entry. "
                    "Minimum 10% Under Keel Clearance (UKC) strictly enforced."
                )
            ),
            PortConstraint(
                port_id="vizag",
                max_loa=290.0,
                max_beam=45.0,
                max_draft_cd=16.5,
                air_draft_limit=21.0,
                min_ukc_pct=10.0,
                daily_discharge_rate_tpd=40000,
                advisory_notice=(
                    "Harbour Master Advisory: Outer Harbour accepts up to 200,000 DWT. "
                    "Deep water channel with 16.5m draft at high water. "
                    "Air draft restriction under conveyor: 21.0m."
                )
            ),
            PortConstraint(
                port_id="dhamra",
                max_loa=315.0,
                max_beam=50.0,
                max_draft_cd=18.0,
                air_draft_limit=24.0,
                min_ukc_pct=10.0,
                daily_discharge_rate_tpd=50000,
                advisory_notice=(
                    "Harbour Master Advisory: All-weather deep water port. "
                    "Capesize vessels up to 18.0m draft berthed without tidal delay. "
                    "Dual-line unloader discharge rate: 50,000 TPD."
                )
            ),
        ]
        db.add_all(constraints_data)
        db.commit()
        print(f"Seeded {len(constraints_data)} port constraints.")

        # 3. Routes
        routes_data = [
            Route(
                id="australia-paradip",
                origin_port="Newcastle",
                origin_country="Australia",
                destination_port_id="paradip",
                primary_cargo="Coal",
                typical_vessel_class="Capesize",
                distance_nautical_miles=5400,
                average_transit_days=18.0
            ),
            Route(
                id="australia-vizag",
                origin_port="Gladstone",
                origin_country="Australia",
                destination_port_id="vizag",
                primary_cargo="Coal",
                typical_vessel_class="Panamax",
                distance_nautical_miles=5150,
                average_transit_days=16.5
            ),
            Route(
                id="indonesia-dhamra",
                origin_port="Taboneo",
                origin_country="Indonesia",
                destination_port_id="dhamra",
                primary_cargo="Coal",
                typical_vessel_class="Supramax",
                distance_nautical_miles=2450,
                average_transit_days=7.5
            ),
        ]
        db.add_all(routes_data)
        db.commit()
        print(f"Seeded {len(routes_data)} routes.")

        # 4. Vessels
        vessels_data = [
            Vessel(
                id="capesize",
                name="Capesize Bulk Carrier",
                vessel_class="Capesize",
                dwt=180000,
                loa=292.0,
                beam=45.0,
                design_draft=14.5,
                daily_demurrage_rate=22500.00
            ),
            Vessel(
                id="kamsarmax",
                name="Kamsarmax Bulk Carrier",
                vessel_class="Kamsarmax",
                dwt=82000,
                loa=229.0,
                beam=32.2,
                design_draft=14.4,
                daily_demurrage_rate=18500.00
            ),
            Vessel(
                id="panamax",
                name="Panamax Bulk Carrier",
                vessel_class="Panamax",
                dwt=75000,
                loa=225.0,
                beam=32.2,
                design_draft=13.8,
                daily_demurrage_rate=17500.00
            ),
            Vessel(
                id="supramax",
                name="Supramax Bulk Carrier",
                vessel_class="Supramax",
                dwt=58000,
                loa=199.9,
                beam=32.2,
                design_draft=12.8,
                daily_demurrage_rate=15000.00
            ),
            Vessel(
                id="handysize",
                name="Handysize Bulk Carrier",
                vessel_class="Handysize",
                dwt=38000,
                loa=180.0,
                beam=28.4,
                design_draft=10.2,
                daily_demurrage_rate=12000.00
            ),
        ]
        db.add_all(vessels_data)
        db.commit()
        print(f"Seeded {len(vessels_data)} vessel classes.")

        # 5. Data Sources Metadata
        metadata_records = [
            DataSourceMetadata(
                source_name="FreightIQ Prototype Benchmark",
                collection_date=date.today(),
                confidence_rating="High (Calibrated Prototype)",
                update_cadence="Daily Simulated",
                description="Deterministic historical benchmark freight series calibrated for SIH26006 research demo.",
                is_simulated=True
            ),
            DataSourceMetadata(
                source_name="Baltic Exchange API Adapter (Planned)",
                collection_date=None,
                confidence_rating="Verified Market Source",
                update_cadence="Daily Real-Time Feed",
                description="Live adapter for Baltic Capesize (BCI), Panamax (BPI), and Supramax (BSI) indices.",
                is_simulated=False
            ),
            DataSourceMetadata(
                source_name="Indian Major Ports Bathymetry (Port Gazettes)",
                collection_date=date(2026, 1, 15),
                confidence_rating="Official Hydrographic Data",
                update_cadence="Quarterly",
                description="Permissible draft, LOA, beam, and Under Keel Clearance regulations for Paradip, Vizag, and Dhamra.",
                is_simulated=False
            )
        ]
        db.add_all(metadata_records)
        db.commit()
        print(f"Seeded {len(metadata_records)} data source metadata records.")

        # 6. Historical Freight Rates (30 Days per route)
        today = date.today()
        rates_to_insert = []

        # Lane 1: Newcastle ➔ Paradip (Rates softening towards spot $19.85)
        lane1_history = [
            22.40, 22.25, 22.10, 21.95, 21.80, 21.70, 21.65, 21.50,
            21.40, 21.30, 21.15, 21.05, 20.90, 20.80, 20.75, 20.60,
            20.50, 20.40, 20.35, 20.20, 20.10, 20.05, 20.00, 19.95,
            19.90, 19.88, 19.85, 19.85, 19.85, 19.85
        ]
        for i, val in enumerate(reversed(lane1_history)):
            r_date = today - timedelta(days=i)
            rates_to_insert.append(FreightRate(
                route_id="australia-paradip",
                rate_date=r_date,
                spot_rate=round(val, 2),
                currency="USD",
                unit="MT",
                data_source="FreightIQ Prototype Benchmark",
                is_simulated=True
            ))

        # Lane 2: Gladstone ➔ Vizag (Rates rallying towards spot $16.30)
        lane2_history = [
            14.20, 14.35, 14.40, 14.50, 14.65, 14.80, 14.90, 15.05,
            15.15, 15.20, 15.30, 15.35, 15.40, 15.50, 15.60, 15.70,
            15.80, 15.85, 15.90, 16.00, 16.05, 16.10, 16.15, 16.20,
            16.22, 16.25, 16.28, 16.30, 16.30, 16.30
        ]
        for i, val in enumerate(reversed(lane2_history)):
            r_date = today - timedelta(days=i)
            rates_to_insert.append(FreightRate(
                route_id="australia-vizag",
                rate_date=r_date,
                spot_rate=round(val, 2),
                currency="USD",
                unit="MT",
                data_source="FreightIQ Prototype Benchmark",
                is_simulated=True
            ))

        # Lane 3: Taboneo ➔ Dhamra (Rates steady towards spot $11.40)
        lane3_history = [
            10.40, 10.45, 10.50, 10.60, 10.65, 10.70, 10.80, 10.85,
            10.90, 10.95, 11.00, 11.05, 11.10, 11.12, 11.15, 11.20,
            11.22, 11.25, 11.28, 11.30, 11.32, 11.35, 11.36, 11.38,
            11.38, 11.39, 11.40, 11.40, 11.40, 11.40
        ]
        for i, val in enumerate(reversed(lane3_history)):
            r_date = today - timedelta(days=i)
            rates_to_insert.append(FreightRate(
                route_id="indonesia-dhamra",
                rate_date=r_date,
                spot_rate=round(val, 2),
                currency="USD",
                unit="MT",
                data_source="FreightIQ Prototype Benchmark",
                is_simulated=True
            ))

        db.add_all(rates_to_insert)
        db.commit()
        print(f"Seeded {len(rates_to_insert)} historical freight rate records.")

        print("\nSUCCESS: FreightIQ database seeded successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
