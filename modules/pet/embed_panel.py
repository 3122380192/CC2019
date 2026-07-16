"""PET panel embedded inside ACC2019 (tkinter host)."""

import os
import sys

import customtkinter as ctk


def create_pet_panel(master, pet_path=None):
    pet_path = pet_path or os.path.dirname(os.path.abspath(__file__))
    if pet_path not in sys.path:
        sys.path.insert(0, pet_path)

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    from app import PhotoshopAutoGUI

    return PhotoshopAutoGUI(master=master, embedded=True)