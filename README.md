# Mapa podróży 🌍

Aplikacja na Androida napisana w Pythonie (framework **Kivy**).
Pokazuje polityczną mapę świata z granicami państw. Dotknij państwa,
naciśnij **„Byłem tu”** – państwo zmieni kolor na zielony.

## Co potrafi

- mapa polityczna świata (242 państwa i terytoria, polskie nazwy),
- przesuwanie jednym palcem, przybliżanie dwoma palcami lub podwójnym
  dotknięciem, przyciski **+ / – / globus** (powrót do całego świata),
- dotknięcie państwa → nazwa i kontynent na dole + przycisk
  **Byłem tu** / **Usuń**,
- odwiedzone państwa są zielone (sąsiednie w lekko różnych odcieniach),
- małe państwa (Watykan, Monako, Malta, wyspy…) mają kropki, żeby dało się
  je trafić palcem,
- licznik: ile państw odwiedzono i jaki to procent lądów świata,
- **Lista** państw z wyszukiwarką (wpisz „slowacja” – znajdzie „Słowacja”),
  filtrami *Wszystkie / Odwiedzone / Do odwiedzenia* i przyciskiem **Mapa**,
  który pokazuje państwo na mapie,
- wszystko zapisuje się w telefonie (działa bez internetu),
- przycisk „wstecz” w telefonie wraca z listy do mapy.

## Pliki

| Plik | Co to jest |
|---|---|
| `main.py` | cała aplikacja |
| `data/world.json` | granice państw (gotowe, już podzielone na trójkąty) |
| `assets/` | ikona i ekran startowy |
| `buildozer.spec` | ustawienia budowania APK |
| `.github/workflows/build-apk.yml` | automatyczne budowanie APK na GitHubie |
| `tools/prepare_data.py` | skrypt, który wygenerował `world.json` (nie trzeba go uruchamiać) |

## Uruchomienie na komputerze (do testów)

```bash
pip install kivy==2.3.1
python main.py
```

Na komputerze: przeciąganie myszą przesuwa mapę, kółko myszy przybliża.

## Jak zrobić plik APK na telefon

Buildozer (narzędzie do budowania APK) działa tylko na Linuksie. Masz dwie
drogi:

### Sposób A – GitHub (najprościej, działa też z Windowsa)

1. Załóż konto na github.com i utwórz nowe repozytorium.
2. Wgraj do niego **całą zawartość** tego folderu (razem z ukrytym folderem
   `.github`). Najłatwiej: *Add file → Upload files* i przeciągnij pliki,
   a folder `.github/workflows/build-apk.yml` utwórz przez *Add file →
   Create new file* wpisując tę ścieżkę jako nazwę i wklejając zawartość.
3. Wejdź w zakładkę **Actions** – budowanie rusza samo (albo kliknij
   *Zbuduj APK → Run workflow*). Pierwsze trwa ok. 20–40 minut.
4. Po zakończeniu kliknij w zakończone zadanie → na dole **Artifacts →
   MapaPodrozy-apk** → pobierzesz ZIP z plikiem `.apk`.
5. Skopiuj APK na telefon i otwórz go. Android poprosi o zgodę na
   instalację z nieznanego źródła – zezwól.

### Sposób B – na własnym komputerze (Linux lub Windows + WSL2 z Ubuntu)

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv \
  autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
  libtinfo6 cmake libffi-dev libssl-dev automake autopoint gettext

python3 -m venv ~/bz && source ~/bz/bin/activate
pip install buildozer "cython<3" setuptools

cd mapa_podrozy
buildozer -v android debug
```

Gotowy plik pojawi się w folderze `bin/`. Jeśli masz telefon podłączony
kablem z włączonym debugowaniem USB, możesz od razu zainstalować i
uruchomić: `buildozer android deploy run logcat`.

> Pierwsze budowanie pobiera Android SDK/NDK (kilka GB) i trwa długo –
> kolejne są już szybkie.

## Zmiany, które łatwo zrobić samemu

- **Kolory** – na górze `main.py` (`VISITED`, `PALETTE`, `OCEAN`…).
- **Napis na przycisku** – szukaj `'Byłem tu'` w `main.py`.
- **Nazwa aplikacji** – `title` w `buildozer.spec`.

## Dane

Granice państw: [Natural Earth](https://www.naturalearthdata.com/)
1:50m (domena publiczna). Przebieg granic w miejscach spornych
jest zgodny z domyślnym widokiem Natural Earth.
