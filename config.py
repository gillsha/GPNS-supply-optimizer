import os

class Config:
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:liza@localhost:5432/transport_db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False