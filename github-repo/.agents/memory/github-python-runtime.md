---
name: GitHub Python bot çalışma ortamı
description: GitHub’dan aktarılan Python projelerinin Replit çalışma akışıyla uyumu
---

Aktarılan Python bot projeleri, depoda `.venv` klasörü bulunmayabileceği için çalışma akışında `.venv/bin/python` varsaymamalı; Replit’in etkin Python modülündeki `python` komutu kullanılmalı.

**Why:** Depodaki sanal ortam klasörleri genellikle `.gitignore` ile hariç tutulur. Bu nedenle GitHub aktarımı sonrasında `.venv/bin/python` çalıştırıcısı mevcut olmayabilir.

**How to apply:** Python bağımlılıklarını proje gereksinimlerinden kurduktan sonra workflow komutunu `python main.py` gibi etkin ortamı kullanan bir komuta ayarla ve bot loglarında Gateway bağlantısını doğrula.