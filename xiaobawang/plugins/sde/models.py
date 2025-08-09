from sqlalchemy import Boolean, Column, Float, Index, Integer, Numeric, String, Text

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
    useBasePrice = Column(Boolean)
    anchored = Column(Boolean)
    anchorable = Column(Boolean)
    fittableNonSingleton = Column(Boolean)
    published = Column(Boolean)

    __table_args__ = (Index("ix_invGroups_categoryID", "categoryID"),)


class InvCategories(Base):
    __tablename__ = "invCategories"

    categoryID = Column(Integer, primary_key=True)
    categoryName = Column(String(100))
    iconID = Column(Integer)
    published = Column(Boolean)


class TrnTranslations(Base):
    __tablename__ = "trnTranslations"

    tcID = Column(Integer, primary_key=True)
    keyID = Column(Integer, primary_key=True)
    languageID = Column(String(50), primary_key=True)
    text = Column(Text, nullable=False)
