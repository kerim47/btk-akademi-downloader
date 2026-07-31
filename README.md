# 🎓 BTK Akademi Video İndirici

[![GitHub release](https://img.shields.io/github/v/release/kerim47/btk-akademi-downloader?color=blue&style=for-the-badge)](https://github.com/kerim47/btk-akademi-downloader/releases)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/kerim47/btk-akademi-downloader?style=for-the-badge)](https://github.com/kerim47/btk-akademi-downloader/stargazers)

BTK Akademi platformundaki eğitim videolarını seçmeli veya toplu olarak bilgisayarınıza indirmenizi sağlayan modern, gelişmiş ve kullanıcı dostu masaüstü uygulaması (PySide6 & `yt-dlp`).

---

## ✨ Özellikler

- 📦 **Tek Başına Çalışabilir Binary (No Python Required):** Herhangi bir Python kurulumuna ihtiyaç duymadan doğrudan çalıştırılabilen masaüstü uygulaması.
- 🌐 **Otomatik Çoklu Platform Desteği (GitHub Actions):** Linux, Windows (`.exe`) ve macOS binary dosyaları her yeni sürümde otomatik derlenir.
- 🎯 **Gelişmiş Seçim Seçenekleri:** 
  - Dersleri ve bölümleri ağaç (tree) yapısında görüntüleme.
  - Tek tek veya toplu ders seçimi.
  - Sağ tık menüsü ile **"Sadece Bu Dersi Seç"** veya **"Sadece Bu Bölümü Seç"**.
  - **Tümünü Seç / Seçimi Temizle** ve **Tümünü Aç / Tümünü Kapat** butonları.
- 🚀 **Otomatik Kayıt Desteği:** İndirme öncesinde kursa kaydolmamışsanız arka planda otomatik kayıt talebi gönderir.
- 🔄 **404 Hata Toleransı & Otomatik Yeniden Deneme:** BTK Akademi sunucularındaki kayıt senkronizasyonu gecikmelerine karşı 404 yanıtı alındığında otomatik yeniden deneme yapar.
- ⚡ **Yüksek Hızlı & Yerel HLS İndirme:** `yt-dlp`'nin dahili HLS motoru ile videolar doğrudan ve hızlı bir şekilde indirilir.
- 📁 **Düzenli Klasörleme:** Videoları bölüm numarası ve adına göre otomatik klasörler halinde düzenler (örneğin: `01_Giriş/01_Tanıtım.mp4`).
- 🌙 **Modern Koyu Tema (Dark Mode):** Catppuccin stilinde göz yormayan koyu tema ve tam ekran desteği.
- 📊 **Detaylı Canlı Günlük & İlerleme Çubuğu:** Anlık indirme hızı, kalan süre, video bazlı ve genel kurs ilerleme durumu.

---

## 🔑 Access Token Nasıl Alınır?

BTK Akademi API istekleri için hesabınıza ait `Access Token` gereklidir. Token almak çok kolaydır:

1. [BTK Akademi](https://www.btkakademi.gov.tr/) sitesine gidin ve hesabınızla giriş yapın.
2. Klavyenizden **F12** tuşuna basarak **Geliştirici Araçları'nı (DevTools)** açın.
3. Üst menüden **Network (Ağ)** sekmesine geçin.
4. Sayfayı yenileyin veya herhangi bir kurs sayfasına gidin.
5. Sol listeden `service/v1` içeren herhangi bir isteğe tıklayın.
6. Sağ taraftaki **Headers (Başlıklar)** sekmesinde **Request Headers** altında `Authorization` başlığını bulun.
7. `Bearer ` ekinden sonra gelen uzun metni (token) kopyalayın ve uygulamadaki **Access Token** alanına yapıştırın.

> 💡 **Not:** Token bilginiz uygulamanın kendi ayarlarında güvenli şekilde saklanır, tekrar tekrar girmeniz gerekmez.

---

## 🚀 Hazır Binary İndirme (Kurulum Gerektirmez)

Python yüklemeden doğrudan uygulamayı çalıştırmak için **[Releases](https://github.com/kerim47/btk-akademi-downloader/releases)** sayfasından sisteminize uygun dosyayı indirebilirsiniz:

- 🪟 **Windows:** `BTK_Downloader-Windows-x64.exe`
- 🐧 **Linux:** `BTK_Downloader-Linux-x86_64`
- 🍏 **macOS:** `BTK_Downloader-macOS`

---

## 🛠️ Geliştirici Kurulumu (Kaynak Koddan Çalıştırma)

Projeyi kaynak koddan çalıştırmak veya katkıda bulunmak isterseniz:

### 1. Repoyu Klonlayın
```bash
git clone https://github.com/kerim47/btk-akademi-downloader.git
cd btk-akademi-downloader
```

### 2. Sanal Ortam (Virtual Environment) Oluşturun ve Aktifleştirin
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Bağımlılıkları Yükleyin
```bash
pip install --upgrade pip
pip install -e .
```

### 4. Uygulamayı Başlatın
```bash
btk-downloader
# veya doğrudan script ile:
python btk_downloader.py
```

---

## 🏗️ Kendi Binary Dosyanızı Derleme (PyInstaller)

Projenizi PyInstaller ile tek bir çalıştırılabilir binary dosyaya dönüştürmek için:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name "BTK_Downloader" btk_downloader.py
```
Derlenen dosya `dist/` klasörü içinde oluşacaktır.

---

## 📜 Lisans

Bu proje **MIT Lisansı** altında lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakabilirsiniz.

---

### ⚠️ Sorumluluk Reddi (Disclaimer)
Bu araç yalnızca kişisel eğitim ve yedekleme amacıyla geliştirilmiştir. BTK Akademi materyallerinin telif hakları ilgili platforma ve içerik üreticilerine aittir.
