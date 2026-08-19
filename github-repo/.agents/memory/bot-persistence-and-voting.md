---
name: Bot verisi ve Top.gg
description: Discord botunda kalıcı veritabanı ve Top.gg erişim kapısı kararları
---

Bot verileri host makinesine bağlı SQLite yerine Replit’in yönetilen PostgreSQL veritabanında tutulmalı. Discord snowflake ID’leri PostgreSQL’de `BIGINT` olarak saklanmalı. Top.gg ile korunan özellikler token yoksa veya kontrol API’si hata verirse açık bırakılmamalı; aksi halde ücretlendirme/oy kapısı sessizce devre dışı kalır.

**Why:** Yerel SQLite host/depolama değişimlerinde garanti vermez; Discord ID’leri 32-bit `INTEGER` sınırını aşar; izin veren hata geri dönüşü de Top.gg kapısını etkisizleştirir.

**How to apply:** Bot veritabanı bağlantısında `BOT_DATABASE_URL` yoksa `DATABASE_URL` kullan, kullanıcı ve sunucu kimliklerini `BIGINT` tanımla ve oy doğrulamasında başarısız sonucu `False` kabul et.