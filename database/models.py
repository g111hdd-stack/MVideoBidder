from sqlalchemy import Column, DateTime, String, Integer
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import UniqueConstraint, MetaData, Identity, ForeignKey


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class Market(Base):
    __tablename__ = 'markets'

    id = Column(Integer, Identity(), primary_key=True)
    marketplace = Column(String(length=255),
                         ForeignKey('marketplaces.marketplace', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    name_company = Column(String(length=255), nullable=False)
    phone = Column(String(length=255), ForeignKey('connects.phone', ondelete='CASCADE', onupdate='CASCADE'),
                   nullable=False)
    entrepreneur = Column(String(length=255), nullable=True)
    client_id = Column(String(length=255), nullable=True)

    marketplace_info = relationship("Marketplace", back_populates="markets")
    connect_info = relationship("Connect", back_populates="markets")

    __table_args__ = (
        UniqueConstraint('marketplace', 'name_company', 'phone', name='markets_unique'),
        UniqueConstraint('marketplace', 'name_company', name='market_unique'),
    )


class Marketplace(Base):
    __tablename__ = 'marketplaces'

    marketplace = Column(String(length=255), primary_key=True, nullable=False)
    link = Column(String(length=1000), nullable=False)
    domain = Column(String(length=255), nullable=False)

    markets = relationship("Market", back_populates="marketplace_info")


class Connect(Base):
    __tablename__ = 'connects'

    phone = Column(String(length=255), primary_key=True, nullable=False)
    proxy = Column(String(length=255), nullable=False)
    mail = Column(String(length=255), nullable=False)
    token = Column(String(length=255), nullable=False)
    pass_mail = Column(String(length=255), nullable=True)

    markets = relationship("Market", back_populates="connect_info")

    __table_args__ = (
        UniqueConstraint('phone', 'proxy', name='connects_unique'),
    )


class User(Base):
    __tablename__ = 'users'

    user = Column(String(length=255), primary_key=True, nullable=False)
    password = Column(String(length=255), nullable=False)
    name = Column(String(length=255), default=None, nullable=True)
    group = Column(String(length=255), ForeignKey('group_table.group', ondelete='CASCADE', onupdate='CASCADE'),
                   nullable=False)

class PhoneMessage(Base):
    __tablename__ = 'phone_message'

    id = Column(Integer, Identity(), primary_key=True)
    user = Column(String(length=255), ForeignKey('users.user', ondelete='SET NULL', onupdate='CASCADE'),
                  nullable=False)
    phone = Column(String(length=255), ForeignKey('connects.phone', ondelete='CASCADE', onupdate='CASCADE'),
                   nullable=False)
    marketplace = Column(String(length=255),
                         ForeignKey('marketplaces.marketplace', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    time_request = Column(DateTime, nullable=False)
    time_response = Column(DateTime, default=None, nullable=True)
    message = Column(String(length=255), default=None, nullable=True)
