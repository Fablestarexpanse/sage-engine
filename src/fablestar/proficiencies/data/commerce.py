"""Commerce domain leaf definitions (35)."""

from __future__ import annotations

LeafRow = tuple[str, dict[str, float]]


def commerce_leaves() -> list[LeafRow]:
    return [
        ("commerce.agriculture.soil_farming", {"FRT": 0.3, "ACU": 0.4, "RSV": 0.3}),
        ("commerce.agriculture.hydroponics", {"ACU": 0.5, "RFX": 0.3, "RSV": 0.2}),
        ("commerce.agriculture.bio_cultivation", {"ACU": 0.5, "RSV": 0.3, "FRT": 0.2}),
        ("commerce.agriculture.arboriculture", {"FRT": 0.3, "ACU": 0.4, "RSV": 0.3}),
        ("commerce.agriculture.pest_management", {"ACU": 0.4, "FRT": 0.3, "RFX": 0.3}),
        ("commerce.agriculture.harvest_processing", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("commerce.agriculture.soil_science", {"ACU": 0.6, "RSV": 0.2, "FRT": 0.2}),
        ("commerce.agriculture.climate_adaptation", {"ACU": 0.4, "RSV": 0.3, "FRT": 0.3}),
        ("commerce.animal_husbandry.livestock_mgmt", {"FRT": 0.3, "ACU": 0.4, "PRS": 0.3}),
        ("commerce.animal_husbandry.creature_breeding", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("commerce.animal_husbandry.veterinary", {"ACU": 0.4, "RFX": 0.3, "FRT": 0.3}),
        ("commerce.animal_husbandry.aquaculture", {"ACU": 0.4, "FRT": 0.3, "RSV": 0.3}),
        ("commerce.trading.appraisal", {"ACU": 0.5, "PRS": 0.3, "RSV": 0.2}),
        ("commerce.trading.negotiation", {"PRS": 0.5, "ACU": 0.3, "RSV": 0.2}),
        ("commerce.trading.market_analysis", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("commerce.trading.smuggling", {"ACU": 0.3, "RFX": 0.3, "PRS": 0.2, "RSV": 0.2}),
        ("commerce.trading.contracts", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("commerce.trading.speculation", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("commerce.resource_extraction.mining", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("commerce.resource_extraction.deep_mining", {"FRT": 0.3, "ACU": 0.4, "RSV": 0.3}),
        ("commerce.resource_extraction.fluid_harvesting", {"ACU": 0.4, "RFX": 0.4, "FRT": 0.2}),
        ("commerce.resource_extraction.energy_tapping", {"ACU": 0.5, "RSV": 0.3, "FRT": 0.2}),
        ("commerce.resource_extraction.forestry", {"FRT": 0.3, "ACU": 0.4, "RSV": 0.3}),
        ("commerce.logistics.cargo_handling", {"FRT": 0.4, "ACU": 0.3, "RFX": 0.3}),
        ("commerce.logistics.route_planning", {"ACU": 0.5, "RSV": 0.3, "PRS": 0.2}),
        ("commerce.logistics.inventory_mgmt", {"ACU": 0.5, "RSV": 0.3, "RFX": 0.2}),
        ("commerce.logistics.supply_chain", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("commerce.enterprise.shop_management", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("commerce.enterprise.venture_planning", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("commerce.enterprise.franchise_ops", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
        ("commerce.enterprise.real_estate", {"ACU": 0.4, "PRS": 0.4, "RSV": 0.2}),
        ("commerce.property.interior_design", {"ACU": 0.3, "PRS": 0.4, "RFX": 0.3}),
        ("commerce.property.property_management", {"ACU": 0.4, "RSV": 0.3, "PRS": 0.3}),
        ("commerce.property.landlording", {"PRS": 0.4, "ACU": 0.3, "RSV": 0.3}),
        ("commerce.property.development", {"ACU": 0.4, "PRS": 0.3, "RSV": 0.3}),
    ]
