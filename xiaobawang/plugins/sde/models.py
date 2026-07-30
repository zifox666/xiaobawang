from sqlalchemy import Boolean, Column, Float, Index, Integer, Numeric, SmallInteger, String, Text

from .db import Base

TC_TYPES_ID = 8
TC_GROUP_ID = 7
TC_CATEGORY_ID = 6


class InvFlags(Base):
    __tablename__ = "invFlags"

    flagID = Column(Integer, primary_key=True)
    flagName = Column(String(200))
    flagText = Column(String(100))
    orderID = Column(Integer)


class InvTypes(Base):
    __tablename__ = "invTypes"

    typeID = Column(Integer, primary_key=True)
    groupID = Column(Integer)
    typeName = Column(String(100))
    description = Column(Text)
    mass = Column(Float)
    volume = Column(Float)
    capacity = Column(Float)
    portionSize = Column(Integer)
    raceID = Column(Integer)
    basePrice = Column(Numeric(19, 4))
    published = Column(Boolean)
    marketGroupID = Column(Integer)
    iconID = Column(Integer)
    soundID = Column(Integer)
    graphicID = Column(Integer)

    __table_args__ = (Index("ix_invTypes_groupID", "groupID"),)


class InvGroups(Base):
    __tablename__ = "invGroups"

    groupID = Column(Integer, primary_key=True)
    categoryID = Column(Integer)
    groupName = Column(String(100))
    iconID = Column(Integer)
    useBasePrice = Column(SmallInteger)
    anchored = Column(SmallInteger)
    anchorable = Column(SmallInteger)
    fittableNonSingleton = Column(SmallInteger)
    published = Column(SmallInteger)

    __table_args__ = (Index("ix_invGroups_categoryID", "categoryID"),)


class InvCategories(Base):
    __tablename__ = "invCategories"

    categoryID = Column(Integer, primary_key=True)
    categoryName = Column(String(100))
    iconID = Column(Integer)
    published = Column(SmallInteger)


class DgmTypeAttributes(Base):
    __tablename__ = "dgmTypeAttributes"

    typeID = Column(Integer, primary_key=True)
    attributeID = Column(Integer, primary_key=True)
    valueInt = Column(Integer)
    valueFloat = Column(Float)

    __table_args__ = (Index("ix_dgmTypeAttributes_attributeID", "attributeID"),)


class DgmAttributeTypes(Base):
    __tablename__ = "dgmAttributeTypes"

    attributeID = Column(Integer, primary_key=True)
    attributeName = Column(String(100))
    description = Column(String(1000))
    iconID = Column(Integer)
    defaultValue = Column(Float)
    published = Column(Boolean)
    displayName = Column(String(150))
    unitID = Column(Integer)
    stackable = Column(Boolean)
    highIsGood = Column(Boolean)
    categoryID = Column(Integer)


class DgmEffects(Base):
    __tablename__ = "dgmEffects"

    effectID = Column(Integer, primary_key=True)
    effectName = Column(String(400))
    effectCategory = Column(Integer)
    published = Column(Boolean)
    displayName = Column(String(100))


class DgmTypeEffects(Base):
    __tablename__ = "dgmTypeEffects"

    typeID = Column(Integer, primary_key=True)
    effectID = Column(Integer, primary_key=True)
    isDefault = Column(Boolean)


class EveUnits(Base):
    __tablename__ = "eveUnits"

    unitID = Column(Integer, primary_key=True)
    unitName = Column(String(100))
    displayName = Column(String(50))
    description = Column(String(1000))


class EveIcons(Base):
    __tablename__ = "eveIcons"

    iconID = Column(Integer, primary_key=True)
    iconFile = Column(String(500))
    description = Column(Text)


class InvTraits(Base):
    __tablename__ = "invTraits"

    traitID = Column(Integer, primary_key=True)
    typeID = Column(Integer)
    skillID = Column(Integer)
    bonus = Column(Float)
    bonusText = Column(Text)
    unitID = Column(Integer)


class TrnTranslations(Base):
    __tablename__ = "trnTranslations"

    tcID = Column(Integer, primary_key=True)
    keyID = Column(Integer, primary_key=True)
    languageID = Column(String(50), primary_key=True)
    text = Column(Text, nullable=False)


class MapSolarSystemJumps(Base):
    __tablename__ = "mapSolarSystemJumps"

    fromRegionID = Column(Integer)
    fromConstellationID = Column(Integer)
    fromSolarSystemID = Column(Integer, primary_key=True)
    toSolarSystemID = Column(Integer, primary_key=True)
    toConstellationID = Column(Integer)
    toRegionID = Column(Integer)
