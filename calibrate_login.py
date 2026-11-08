# -*- coding: utf-8 -*-
"""
سكريبت معايرة Riot Client.

طريقة الاستخدام:
  1. افتح Riot Client (سيب نافذة الدخول ظاهرة)
  2. من طرفية في فولدر المشروع اكتب:
         python calibrate_login.py
  3. اتبع التعليمات (حرّك الماوس → دوس F8)
  4. خلاص. يوبي هيفتكر الإحداثيات للأبد.
"""

from login_calibration import calibrate_riot


if __name__ == "__main__":
    calibrate_riot()