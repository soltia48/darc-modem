from darc.section_tt import SectionTravelTimeDataUnit
from .l5_data import GenericDataUnit
from .parking import ParkingDataUnit
from .restriction_accident import RestrictionAccidentDataUnit
from .travel_time import TravelTimeDataUnit


def data_unit_from_generic(generic: GenericDataUnit):
    """
    Wrap *GenericDataUnit* into the appropriate typed decoder.
    """
    if generic.data_unit_parameter == 0x40:
        return TravelTimeDataUnit.from_generic(generic)
    elif generic.data_unit_parameter == 0x41:
        return RestrictionAccidentDataUnit.from_generic(generic)
    elif generic.data_unit_parameter == 0x42:
        return ParkingDataUnit.from_generic(generic)
    elif generic.data_unit_parameter == 0x43:
        return SectionTravelTimeDataUnit.from_generic(generic)
    return generic
