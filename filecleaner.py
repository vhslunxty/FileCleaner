#!/usr/bin/env python3
import argparse
import hashlib
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


class Colors:
    """Codes couleur pour le terminal."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str) -> None:
    """Affiche un titre formaté."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_success(text: str) -> None:
    """Affiche un message de succès."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text: str) -> None:
    """Affiche un avertissement."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str) -> None:
    """Affiche une erreur."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text: str) -> None:
    """Affiche une information."""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def format_size(size_bytes: int) -> str:
    """Formate une taille en bytes en unités lisibles."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def ask_confirmation(message: str) -> bool:
    """Demande une confirmation à l'utilisateur."""
    response = input(f"{Colors.YELLOW}{message} [o/N]: {Colors.END}").strip().lower()
    return response in ('o', 'oui', 'y', 'yes')


class FileCleaner:
    """Classe principale de nettoyage de fichiers."""

    def __init__(self, interactive: bool = False, dry_run: bool = False):
        self.interactive = interactive
        self.dry_run = dry_run
        self.stats = {
            'files_removed': 0,
            'dirs_removed': 0,
            'space_freed': 0,
            'errors': 0
        }

    def _remove_file(self, path: Path, description: str = "") -> bool:
        """Supprime un fichier avec gestion des erreurs."""
        desc = description or str(path)
        if self.interactive:
            if not ask_confirmation(f"Supprimer {desc} ?"):
                print_info(f"Ignoré : {desc}")
                return False

        if self.dry_run:
            print_info(f"[SIMULATION] Suppression : {desc}")
            self.stats['files_removed'] += 1
            self.stats['space_freed'] += path.stat().st_size if path.exists() else 0
            return True

        try:
            size = path.stat().st_size
            path.unlink()
            self.stats['files_removed'] += 1
            self.stats['space_freed'] += size
            print_success(f"Supprimé : {desc}")
            return True
        except (OSError, PermissionError) as e:
            self.stats['errors'] += 1
            print_error(f"Impossible de supprimer {desc} : {e}")
            return False

    def _remove_dir(self, path: Path, description: str = "") -> bool:
        """Supprime un répertoire avec gestion des erreurs."""
        desc = description or str(path)
        if self.interactive:
            if not ask_confirmation(f"Supprimer le dossier {desc} ?"):
                print_info(f"Ignoré : {desc}")
                return False

        if self.dry_run:
            print_info(f"[SIMULATION] Suppression dossier : {desc}")
            self.stats['dirs_removed'] += 1
            try:
                self.stats['space_freed'] += sum(
                    f.stat().st_size for f in path.rglob('*') if f.is_file()
                )
            except (OSError, PermissionError):
                pass
            return True

        try:
            size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            shutil.rmtree(path)
            self.stats['dirs_removed'] += 1
            self.stats['space_freed'] += size
            print_success(f"Supprimé : {desc}")
            return True
        except (OSError, PermissionError) as e:
            self.stats['errors'] += 1
            print_error(f"Impossible de supprimer {desc} : {e}")
            return False

    def clean_temp(self) -> None:
        """Nettoie les fichiers temporaires."""
        print_header("NETTOYAGE DES FICHIERS TEMPORAIRES")

        temp_paths = [
            Path("/tmp"),
            Path("/var/tmp"),
            Path.home() / ".tmp",
            Path.home() / "tmp",
            Path.home() / "temp",
            Path.home() / ".local" / "share" / "Trash" / "files",
            Path.home() / ".local" / "share" / "Trash" / "info",
        ]

        temp_extensions = {
            '.tmp', '.temp', '.swp', '.swo', '.bak', '.old',
            '.~', '.part', '.crdownload', '.download'
        }

        for temp_path in temp_paths:
            if not temp_path.exists():
                continue

            print_info(f"Analyse de {temp_path}...")

            for item in temp_path.iterdir():
                try:
                    if item.is_file():
                        if item.suffix.lower() in temp_extensions:
                            self._remove_file(item)
                        elif self._is_old_file(item, days=7):
                            self._remove_file(item, f"{item} (vieux de +7 jours)")
                    elif item.is_dir():
                        if self._is_old_file(item, days=7):
                            self._remove_dir(item, f"{item} (vieux de +7 jours)")
                except (OSError, PermissionError):
                    continue

        print_info("Recherche de fichiers temporaires dans le home...")
        home = Path.home()
        for ext in temp_extensions:
            try:
                for file_path in home.rglob(f"*{ext}"):
                    if file_path.is_file() and self._is_old_file(file_path, days=3):
                        self._remove_file(file_path)
            except (OSError, PermissionError):
                continue

    def clean_cache(self) -> None:
        """Nettoie les caches."""
        print_header("NETTOYAGE DES CACHES")

        cache_paths = [
            # Cache système
            Path.home() / ".cache",
            Path("/var/cache"),
            # Cache Python
            Path.home() / ".local" / "lib" / "python*" / "site-packages" / "__pycache__",
            # Cache pip
            Path.home() / ".cache" / "pip",
            # Cache npm/yarn
            Path.home() / ".npm" / "_cacache",
            Path.home() / ".yarn" / "cache",
            # Cache Docker
            Path("/var/lib/docker/tmp"),
            # Cache APT
            Path("/var/cache/apt/archives"),
        ]

        print_info("Recherche des caches Python (__pycache__, .pyc)...")
        for pycache_dir in Path.home().rglob("__pycache__"):
            if pycache_dir.is_dir():
                self._remove_dir(pycache_dir)

        for pyc_file in Path.home().rglob("*.pyc"):
            if pyc_file.is_file():
                self._remove_file(pyc_file)

        for pyo_file in Path.home().rglob("*.pyo"):
            if pyo_file.is_file():
                self._remove_file(pyo_file)

        for cache_path in cache_paths:
            if not cache_path.exists():
                if '*' in str(cache_path):
                    import glob
                    for matched_path in glob.glob(str(cache_path)):
                        self._clean_cache_dir(Path(matched_path))
                continue
            self._clean_cache_dir(cache_path)

        self._clean_browser_cache()

    def _clean_cache_dir(self, path: Path) -> None:
        """Nettoie un répertoire de cache."""
        if not path.exists():
            return

        print_info(f"Nettoyage de {path}...")
        try:
            for item in path.iterdir():
                if item.is_file():
                    self._remove_file(item)
                elif item.is_dir():
                    self._remove_dir(item)
        except (OSError, PermissionError) as e:
            print_error(f"Accès refusé pour {path}: {e}")

    def _clean_browser_cache(self) -> None:
        """Nettoie les caches des navigateurs."""
        print_info("Recherche des caches de navigateurs...")

        browser_caches = [
            # Chrome/Chromium
            Path.home() / ".cache" / "google-chrome",
            Path.home() / ".cache" / "chromium",
            Path.home() / ".config" / "google-chrome" / "Default" / "Cache",
            Path.home() / ".config" / "chromium" / "Default" / "Cache",
            # Firefox
            Path.home() / ".cache" / "mozilla",
            Path.home() / ".mozilla" / "firefox" / "*" / "cache2",
            # Brave
            Path.home() / ".cache" / "BraveSoftware",
            # Opera
            Path.home() / ".cache" / "opera",
        ]

        for cache_path in browser_caches:
            if '*' in str(cache_path):
                import glob
                for matched in glob.glob(str(cache_path)):
                    self._clean_cache_dir(Path(matched))
            elif cache_path.exists():
                self._clean_cache_dir(cache_path)

    def clean_logs(self, max_age_days: int = 30) -> None:
        """Nettoie les vieux logs."""
        print_header("NETTOYAGE DES LOGS")

        log_paths = [
            Path("/var/log"),
            Path.home() / ".local" / "share" / "log",
            Path.home() / "logs",
            Path.home() / ".logs",
        ]

        log_extensions = {'.log', '.log.1', '.log.2', '.log.3', '.log.old'}

        for log_path in log_paths:
            if not log_path.exists():
                continue

            print_info(f"Analyse de {log_path}...")

            for item in log_path.rglob("*"):
                try:
                    if item.is_file():
                        if (item.suffix.lower() in log_extensions or
                            item.name.endswith('.log') or
                            '.log.' in item.name):
                            if self._is_old_file(item, days=max_age_days):
                                self._remove_file(
                                    item,
                                    f"{item} (log vieux de +{max_age_days} jours)"
                                )
                except (OSError, PermissionError):
                    continue

        print_info(f"Recherche de logs vieux de +{max_age_days} jours...")
        for ext in log_extensions:
            try:
                for log_file in Path.home().rglob(f"*{ext}"):
                    if log_file.is_file() and self._is_old_file(log_file, days=max_age_days):
                        self._remove_file(log_file)
            except (OSError, PermissionError):
                continue

    def find_duplicates(self, paths: list[Path], min_size: int = 0) -> dict[str, list[Path]]:
        """Trouve les fichiers en double par hash."""
        print_header("RECHERCHE DE DOUBLONS")

        hashes = defaultdict(list)
        total_files = 0

        for search_path in paths:
            if not search_path.exists():
                print_warning(f"Chemin inexistant : {search_path}")
                continue

            print_info(f"Analyse de {search_path}...")

            for file_path in search_path.rglob("*"):
                try:
                    if not file_path.is_file():
                        continue

                    size = file_path.stat().st_size
                    if size < min_size:
                        continue

                    total_files += 1
                    file_hash = self._hash_file(file_path)
                    if file_hash:
                        hashes[file_hash].append(file_path)

                except (OSError, PermissionError):
                    continue

        duplicates = {h: files for h, files in hashes.items() if len(files) > 1}

        print_info(f"Fichiers analysés : {total_files}")
        print_info(f"Doublons trouvés : {len(duplicates)} groupes")

        return duplicates

    def clean_duplicates(self, paths: list[Path], min_size: int = 0,
                         keep_oldest: bool = True) -> None:
        """Supprime les fichiers en double, garde un exemplaire."""
        duplicates = self.find_duplicates(paths, min_size)

        if not duplicates:
            print_info("Aucun doublon trouvé.")
            return

        for file_hash, files in duplicates.items():
            files_sorted = sorted(files, key=lambda p: p.stat().st_mtime)

            if keep_oldest:
                keep = files_sorted[0]  
                to_remove = files_sorted[1:]
            else:
                keep = files_sorted[-1] 
                to_remove = files_sorted[:-1]

            print_info(f"Conservé : {keep}")

            for dup_file in to_remove:
                self._remove_file(dup_file, f"doublon de {keep.name}")

    def _hash_file(self, path: Path, block_size: int = 65536) -> str | None:
        """Calcule le hash MD5 d'un fichier."""
        try:
            hasher = hashlib.md5()
            with open(path, 'rb') as f:
                while chunk := f.read(block_size):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return None

    def _is_old_file(self, path: Path, days: int) -> bool:
        """Vérifie si un fichier est plus vieux que X jours."""
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            return datetime.now() - mtime > timedelta(days=days)
        except (OSError, PermissionError):
            return False

    def print_stats(self) -> None:
        """Affiche les statistiques de nettoyage."""
        print_header("RAPPORT DE NETTOYAGE")
        print(f"  Fichiers supprimés : {self.stats['files_removed']}")
        print(f"  Dossiers supprimés : {self.stats['dirs_removed']}")
        print(f"  Espace libéré      : {format_size(self.stats['space_freed'])}")
        print(f"  Erreurs            : {self.stats['errors']}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")


def main():
    parser = argparse.ArgumentParser(
        description="FileCleaner - Nettoyeur de fichiers temporaires, cache, logs et doublons",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s --all                    # Tout nettoyer
  %(prog)s --temp --cache           # Temporaires et cache uniquement
  %(prog)s --logs --max-age 7       # Logs de plus de 7 jours
  %(prog)s --duplicates ~/Documents # Chercher les doublons
  %(prog)s --all --interactive      # Mode interactif (confirmation)
  %(prog)s --all --dry-run          # Simulation (ne rien supprimer)
        """
    )

    parser.add_argument('--all', action='store_true',
                        help='Nettoyer tout (temp, cache, logs)')
    parser.add_argument('--temp', action='store_true',
                        help='Nettoyer les fichiers temporaires')
    parser.add_argument('--cache', action='store_true',
                        help='Nettoyer les caches')
    parser.add_argument('--logs', action='store_true',
                        help='Nettoyer les vieux logs')
    parser.add_argument('--duplicates', nargs='+', metavar='PATH',
                        help='Chemins à analyser pour les doublons')
    parser.add_argument('--min-size', type=str, default='0',
                        help='Taille minimale pour les doublons (ex: 1K, 1M, 1G)')
    parser.add_argument('--max-age', type=int, default=30,
                        help='Âge maximal des logs en jours (défaut: 30)')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Demander confirmation avant chaque suppression')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Simulation (ne rien supprimer)')

    args = parser.parse_args()

    if not any([args.all, args.temp, args.cache, args.logs, args.duplicates]):
        args.all = True

    min_size = 0
    if args.min_size:
        size_str = args.min_size.upper()
        multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
        if size_str[-1] in multipliers:
            min_size = int(size_str[:-1]) * multipliers[size_str[-1]]
        else:
            min_size = int(size_str)

    cleaner = FileCleaner(interactive=args.interactive, dry_run=args.dry_run)

    if args.dry_run:
        print_warning("MODE SIMULATION - Aucun fichier ne sera supprimé")

    try:
        if args.all or args.temp:
            cleaner.clean_temp()

        if args.all or args.cache:
            cleaner.clean_cache()

        if args.all or args.logs:
            cleaner.clean_logs(max_age_days=args.max_age)

        if args.duplicates:
            paths = [Path(p).expanduser().resolve() for p in args.duplicates]
            cleaner.clean_duplicates(paths, min_size=min_size)

    except KeyboardInterrupt:
        print_warning("\nOpération interrompue par l'utilisateur.")

    cleaner.print_stats()


if __name__ == '__main__':
    main()
