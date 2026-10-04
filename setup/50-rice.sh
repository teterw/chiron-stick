#!/bin/bash
# Phase 4R: the "Clinic Night" desktop theme, system part. Run it ON the stick, as root. Afterwards
# run setup/51-rice-user.sh as the desktop user, inside their graphical session.
# Usage: sudo setup/50-rice.sh [--dry-run]
#
# Downloads that aren't in Mint's repositories are pinned to the SHA-256 published for that release
# (CLAUDE.md safety rule 7). wallust is built from crates.io with --locked: cargo checks every crate
# against crates.io's checksums. The Rust toolchain used for that is removed again afterwards.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
. "$HERE/lib/common.sh"
parse_args "$@"
[ "$(id -u)" = 0 ] || [ "$DRY_RUN" = 1 ] || die "run as root on the stick"
export DEBIAN_FRONTEND=noninteractive
APT=(apt-get -y -q --no-install-recommends -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

ADW_URL=https://github.com/lassekongo83/adw-gtk3/releases/download/v6.5/adw-gtk3v6.5.tar.xz
ADW_SHA=a81780fadfc432be0fc3d89c4ebb41aa28e4f032d42c36f9789c57dd10cfa41c
FASTFETCH_URL=https://github.com/fastfetch-cli/fastfetch/releases/download/2.69.0/fastfetch-linux-amd64.deb
FASTFETCH_SHA=cd91bc80ba416e2089e4dd40ea087e9e02028aeeb65988f92e17ede8da1c1bda
STARSHIP_URL=https://github.com/starship/starship/releases/download/v1.26.0/starship-x86_64-unknown-linux-musl.tar.gz
STARSHIP_SHA=b7c232b0e8249d8e55a40beb79c5c43a7d370f3f9408bd215deb0170daeaadf3
NERDFONT_URL=https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.1/JetBrainsMono.tar.xz
NERDFONT_SHA=04d5e8f903693f9dd13e16f867e994834e681eb3c72c0d337a770dcda09010cf
WALLUST_VERSION=3.5.1

if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] apt: rofi conky-all fonts-jetbrains-mono xdotool xfce4-windowck-plugin xfce4-genmon-plugin git papirus-icon-theme"
  echo "[dry-run] build the missing Papirus icon caches"
  echo "[dry-run] verified downloads: adw-gtk3 v6.5, fastfetch 2.69.0, starship 1.26.0, JetBrainsMono Nerd Font 3.5.1"
  echo "[dry-run] build wallust $WALLUST_VERSION from crates.io (--locked), then remove the Rust toolchain"
  echo "[dry-run] install rice to /opt/chiron/rice; GRUB theme, Plymouth splash, login screen"
  exit 0
fi

W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
fetch() {  # fetch <url> <sha256> <file>: download and verify, or stop
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c --quiet - || die "checksum mismatch for $1: not installing it"
  echo "verified: $(basename "$1")"
}

echo "===== 1. Packages"
"${APT[@]}" install rofi conky-all fonts-jetbrains-mono xdotool xfce4-windowck-plugin xfce4-genmon-plugin git x11-xserver-utils \
  papirus-icon-theme gtk-update-icon-cache
# Mint's Papirus has no icon caches: its postinst skips them when gtk-update-icon-cache isn't there yet.
# Without a cache every GTK program indexes ~500 icon folders on its own, ~55 MB more RAM each
# (measured: 64 -> 7 MB heap). From now on the package's own trigger keeps the caches current.
for t in Papirus Papirus-Dark; do
  gtk-update-icon-cache --force --quiet "/usr/share/icons/$t"
done

echo "===== 2. Verified downloads"
fetch "$ADW_URL" "$ADW_SHA" "$W/adw.tar.xz"
tar -xJf "$W/adw.tar.xz" -C /usr/share/themes
ls -d /usr/share/themes/adw-gtk3*
fetch "$FASTFETCH_URL" "$FASTFETCH_SHA" "$W/fastfetch.deb"
"${APT[@]}" install "$W/fastfetch.deb"
fetch "$STARSHIP_URL" "$STARSHIP_SHA" "$W/starship.tar.gz"
tar -xzf "$W/starship.tar.gz" -C "$W"
install -m 0755 "$W/starship" /usr/local/bin/starship
fetch "$NERDFONT_URL" "$NERDFONT_SHA" "$W/jbm.tar.xz"
install -d /usr/local/share/fonts/JetBrainsMonoNerd
tar -xJf "$W/jbm.tar.xz" -C /usr/local/share/fonts/JetBrainsMonoNerd --wildcards '*.ttf'
fc-cache -f >/dev/null
fc-list | grep -c "JetBrainsMono Nerd Font" | sed 's/^/Nerd Font faces: /'

echo "===== 3. wallust $WALLUST_VERSION from crates.io (checksums checked by cargo --locked)"
if command -v wallust >/dev/null && wallust --version | grep -q "$WALLUST_VERSION"; then
  echo "already installed: $(wallust --version)"
else
  dpkg-query -W -f='${Package}\n' | sort > "$W/before"
  "${APT[@]}" install rustc-1.91 cargo-1.91 gcc libc6-dev
  dpkg-query -W -f='${Package}\n' | sort > "$W/after"
  CARGO_HOME="$W/cargo" RUSTC=rustc-1.91 cargo-1.91 install wallust --version "$WALLUST_VERSION" --locked --root /usr/local
  wallust --version
  # Remove exactly what the build pulled in (not apt's autoremove: that could take the fallback kernel too)
  comm -13 "$W/before" "$W/after" > "$W/added"
  if [ -s "$W/added" ]; then apt-get purge -y -q $(cat "$W/added"); fi
  echo "removed the Rust toolchain again ($(wc -l < "$W/added") packages)"
fi

echo "===== 4. Theme scripts -> /opt/chiron/rice"
rm -rf /opt/chiron/rice.new
cp -r "$REPO/rice" /opt/chiron/rice.new
chmod 0755 /opt/chiron/rice.new/chiron-rice /opt/chiron/rice.new/get-walls.sh /opt/chiron/rice.new/branding/make-assets.py
rm -rf /opt/chiron/rice
mv /opt/chiron/rice.new /opt/chiron/rice

echo "===== 5. Boot branding: GRUB theme, Plymouth splash + unlock screen, login screen"
python3 /opt/chiron/rice/branding/make-assets.py "$W/assets"
T=/boot/grub/themes/chiron
install -d "$T"
install -m 0644 "$W/assets/background.png" "$W/assets/select_c.png" "$W/assets/select_w.png" "$T/"
install -m 0644 /opt/chiron/rice/branding/grub-theme.txt "$T/theme.txt"
for size in 16 20; do grub-mkfont -s $size -o "$T/dejavu-sans-$size.pf2" /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf; done
grub-mkfont -s 14 -o "$T/dejavu-sans-mono-14.pf2" /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
printf '# Chiron Stick boot menu theme (setup/50-rice.sh)\nGRUB_THEME=%s/theme.txt\n' "$T" > /etc/default/grub.d/99-chiron-theme.cfg
update-grub 2>&1 | grep -E "theme|Found theme" || true

P=/usr/share/plymouth/themes/chiron
rm -rf "$P"
cp -a /usr/share/plymouth/themes/mint-logo "$P"
rm -f "$P/mint-logo.plymouth"
cp "$W/assets/plymouth/"*.png "$P/"
sed -e 's/^Name=.*/Name=Chiron Stick/' -e 's/^Description=.*/Description=Chiron Stick: a heartbeat line while it boots./' \
    -e "s|^ImageDir=.*|ImageDir=$P|" /usr/share/plymouth/themes/mint-logo/mint-logo.plymouth > "$P/chiron.plymouth"
update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth "$P/chiron.plymouth" 250
update-alternatives --set default.plymouth "$P/chiron.plymouth"
update-initramfs -u -k all 2>&1 | tail -n 2

install -d /usr/share/backgrounds/chiron
install -m 0644 "$W/assets/background.png" /usr/share/backgrounds/chiron/login.png
cat > /etc/lightdm/slick-greeter.conf <<'EOF'
# Chiron Stick login screen (setup/50-rice.sh). A fixed image: changing it with every wallpaper
# would mean running something as root on every change.
[Greeter]
background=/usr/share/backgrounds/chiron/login.png
draw-user-backgrounds=false
draw-grid=false
theme-name=adw-gtk3-dark
icon-theme-name=Papirus-Dark
cursor-theme-name=Bibata-Modern-Classic
font-name=Noto Sans 11
show-hostname=true
EOF
echo "System part done. Next, as the desktop user in their session: setup/51-rice-user.sh"
