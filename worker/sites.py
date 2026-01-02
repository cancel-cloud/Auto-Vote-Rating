"""
Definitions for supported voting sites and URL parsing utilities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


_ID_RE = r"(?P<id>[A-Za-z0-9_-]+)"


@dataclass
class VoteSite:
    key: str
    label: str
    vote_url_template: str
    example_url: str
    pattern_sources: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in self.pattern_sources]

    def build_vote_url(self, project_id: str) -> str:
        """Construct a canonical vote URL for this site."""
        if "{projectId}" not in self.vote_url_template:
            raise ValueError(f"vote_url_template missing '{{projectId}}' placeholder for {self.key}")
        return self.vote_url_template.format(projectId=project_id)

    def extract_project_id(self, url: str) -> Optional[str]:
        """Try to extract a project id from the given URL."""
        for pattern in self.patterns:
            match = pattern.search(url)
            if match:
                project_id = match.groupdict().get("id") or (match.groups()[0] if match.groups() else None)
                if project_id:
                    return project_id.strip("/ ")
        return None


def _site(
    key: str,
    template: str,
    example: Optional[str] = None,
    patterns: Optional[List[str]] = None,
    label: Optional[str] = None,
) -> VoteSite:
    """Helper to instantiate VoteSite entries."""
    if example is None:
        example = template.format(projectId="12345")
    if patterns is None:
        escaped = re.escape(key)
        patterns = [fr"{escaped}.+/(?P<id>[A-Za-z0-9_-]+)"]
    return VoteSite(
        key=key,
        label=label or key,
        vote_url_template=template,
        example_url=example,
        pattern_sources=patterns,
    )


SUPPORTED_SITES: Dict[str, VoteSite] = {
    site.key: site
    for site in [
        _site(
            "minecraft-server.eu",
            "https://minecraft-server.eu/vote/index/{projectId}/",
            example="https://minecraft-server.eu/vote/index/208F7/",
            patterns=[rf"minecraft-server\.eu/(?:vote/)?index/{_ID_RE}"],
        ),
        _site(
            "minecraft-serverlist.net",
            "https://www.minecraft-serverlist.net/vote/{projectId}/",
            patterns=[rf"minecraft-serverlist\.net/(?:server/|vote/){_ID_RE}"],
        ),
        _site(
            "topcraft.club",
            "https://topcraft.club/servers/{projectId}/vote/",
            patterns=[rf"topcraft\.(?:club|ru)/servers/{_ID_RE}"],
        ),
        _site(
            "mctop.su",
            "https://mctop.su/servers/{projectId}/vote/",
            patterns=[rf"mctop\.su/servers/{_ID_RE}"],
        ),
        _site(
            "mcrate.su",
            "http://mcrate.su/rate/{projectId}",
            patterns=[rf"mcrate\.su/(?:rate|project)/{_ID_RE}"],
        ),
        _site(
            "minecraftrating.ru",
            "https://minecraftrating.ru/projects/{projectId}/",
            patterns=[rf"minecraftrating\.ru/(?:projects|vote)/{_ID_RE}"],
        ),
        _site(
            "monitoringminecraft.ru",
            "https://monitoringminecraft.ru/top/{projectId}/vote",
            patterns=[rf"monitoringminecraft\.ru/top/{_ID_RE}"],
        ),
        _site(
            "ionmc.top",
            "https://ionmc.top/projects/{projectId}/vote",
            patterns=[rf"ionmc\.top/projects/{_ID_RE}"],
        ),
        _site(
            "minecraftservers.org",
            "https://minecraftservers.org/vote/{projectId}",
            patterns=[rf"minecraftservers\.org/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "serveur-prive.net",
            "https://serveur-prive.net/minecraft/{projectId}/vote",
            patterns=[rf"serveur-prive\.net/.+/{_ID_RE}/vote"],
        ),
        _site(
            "planetminecraft.com",
            "https://www.planetminecraft.com/server/{projectId}/",
            patterns=[rf"planetminecraft\.com/server/{_ID_RE}"],
        ),
        _site(
            "topg.org",
            "https://topg.org/minecraft/vote/{projectId}",
            patterns=[rf"topg\.org/minecraft/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "minecraft-mp.com",
            "https://minecraft-mp.com/vote/{projectId}",
            patterns=[rf"minecraft-mp\.com/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "minecraft-server-list.com",
            "https://minecraft-server-list.com/vote/{projectId}",
            patterns=[rf"minecraft-server-list\.com/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "serverpact.com",
            "https://serverpact.com/server/{projectId}",
            patterns=[rf"serverpact\.com/\w+/{_ID_RE}"],
        ),
        _site(
            "minecraftiplist.com",
            "https://minecraftiplist.com/server/{projectId}",
            patterns=[rf"minecraftiplist\.com/\w+/{_ID_RE}"],
        ),
        _site(
            "topminecraftservers.org",
            "https://topminecraftservers.org/vote/{projectId}",
            patterns=[rf"topminecraftservers\.org/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "minecraftservers.biz",
            "https://minecraftservers.biz/vote/{projectId}",
            patterns=[rf"minecraftservers\.biz/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "hotmc.ru",
            "https://hotmc.ru/server/{projectId}",
            patterns=[rf"hotmc\.ru/server/{_ID_RE}"],
        ),
        _site(
            "minecraft-server.net",
            "https://minecraft-server.net/vote/{projectId}",
            patterns=[rf"minecraft-server\.net/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "top-games.net",
            "https://top-games.net/minecraft/{projectId}",
            patterns=[rf"top-games\.net/(?:minecraft|server)/{_ID_RE}"],
        ),
        _site(
            "tmonitoring.com",
            "https://tmonitoring.com/server/{projectId}",
            patterns=[rf"tmonitoring\.com/server/{_ID_RE}"],
        ),
        _site(
            "top.gg",
            "https://top.gg/bot/{projectId}",
            patterns=[rf"top\.gg/(?:bot|servers)/{_ID_RE}"],
        ),
        _site(
            "discordbotlist.com",
            "https://discordbotlist.com/bots/{projectId}",
            patterns=[rf"discordbotlist\.com/bots/{_ID_RE}"],
        ),
        _site(
            "discords.com",
            "https://discords.com/bots/{projectId}",
            patterns=[rf"discords\.com/bots/{_ID_RE}"],
        ),
        _site(
            "mmotop.ru",
            "https://mmotop.ru/server/{projectId}",
            patterns=[rf"mmotop\.ru/server/{_ID_RE}"],
        ),
        _site(
            "mc-servers.com",
            "https://mc-servers.com/vote/{projectId}",
            patterns=[rf"mc-servers\.com/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "minecraftlist.org",
            "https://minecraftlist.org/vote/{projectId}",
            patterns=[rf"minecraftlist\.org/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "minecraft-index.com",
            "https://minecraft-index.com/vote/{projectId}",
            patterns=[rf"minecraft-index\.com/(?:vote|server)/{_ID_RE}"],
        ),
        _site(
            "serverlist101.com",
            "https://serverlist101.com/server/{projectId}",
            patterns=[rf"serverlist101\.com/server/{_ID_RE}"],
        ),
        _site(
            "mcserver-list.eu",
            "https://mcserver-list.eu/server/{projectId}",
            patterns=[rf"mcserver-list\.eu/server/{_ID_RE}"],
        ),
        _site(
            "craftlist.org",
            "https://craftlist.org/server/{projectId}",
            patterns=[rf"craftlist\.org/server/{_ID_RE}"],
        ),
        _site(
            "czech-craft.eu",
            "https://czech-craft.eu/server/{projectId}/vote",
            patterns=[rf"czech-craft\.eu/server/{_ID_RE}"],
        ),
        _site(
            "minecraft.buzz",
            "https://minecraft.buzz/server/{projectId}",
            patterns=[rf"minecraft\.buzz/server/{_ID_RE}"],
        ),
        _site(
            "minecraftservery.eu",
            "https://minecraftservery.eu/server/{projectId}",
            patterns=[rf"minecraftservery\.eu/server/{_ID_RE}"],
        ),
        _site(
            "rpg-paradize.com",
            "https://rpg-paradize.com/server/{projectId}",
            patterns=[rf"rpg-paradize\.com/server/{_ID_RE}"],
        ),
        _site(
            "minecraftkrant.nl",
            "https://minecraftkrant.nl/server/{projectId}",
            patterns=[rf"minecraftkrant\.nl/server/{_ID_RE}"],
        ),
        _site(
            "trackyserver.com",
            "https://trackyserver.com/server/{projectId}",
            patterns=[rf"trackyserver\.com/server/{_ID_RE}"],
        ),
        _site(
            "mc-lists.org",
            "https://mc-lists.org/server/{projectId}",
            patterns=[rf"mc-lists\.org/server/{_ID_RE}"],
        ),
        _site(
            "topmcservers.com",
            "https://topmcservers.com/server/{projectId}",
            patterns=[rf"topmcservers\.com/server/{_ID_RE}"],
        ),
        _site(
            "bestservers.com",
            "https://bestservers.com/server/{projectId}",
            patterns=[rf"bestservers\.com/server/{_ID_RE}"],
        ),
        _site(
            "craft-list.net",
            "https://craft-list.net/server/{projectId}",
            patterns=[rf"craft-list\.net/server/{_ID_RE}"],
        ),
        _site(
            "minecraft-servers-list.org",
            "https://minecraft-servers-list.org/server/{projectId}",
            patterns=[rf"minecraft-servers-list\.org/server/{_ID_RE}"],
        ),
        _site(
            "serverliste.net",
            "https://serverliste.net/server/{projectId}",
            patterns=[rf"serverliste\.net/server/{_ID_RE}"],
        ),
        _site(
            "gtop100.com",
            "https://gtop100.com/server/{projectId}",
            patterns=[rf"gtop100\.com/server/{_ID_RE}"],
        ),
        _site(
            "wargm.ru",
            "https://wargm.ru/server/{projectId}",
            patterns=[rf"wargm\.ru/server/{_ID_RE}"],
        ),
        _site(
            "minestatus.net",
            "https://minestatus.net/server/{projectId}",
            patterns=[rf"minestatus\.net/server/{_ID_RE}"],
        ),
        _site(
            "misterlauncher.org",
            "https://misterlauncher.org/server/{projectId}",
            patterns=[rf"misterlauncher\.org/server/{_ID_RE}"],
        ),
    ]
}


def parse_vote_url(url: str) -> Optional[Dict[str, str]]:
    """Try to detect the vote site + project id from a URL."""
    if not url:
        return None
    cleaned = url.strip()
    for site in SUPPORTED_SITES.values():
        project_id = site.extract_project_id(cleaned)
        if project_id:
            normalized = site.build_vote_url(project_id)
            return {
                "siteKey": site.key,
                "projectId": project_id,
                "normalizedUrl": normalized,
                "exampleUrl": site.example_url,
            }
    return None


def get_supported_sites() -> List[Dict[str, str]]:
    """Return sites formatted for API responses."""
    return [
        {
            "key": site.key,
            "label": site.label,
            "exampleUrl": site.example_url,
            "template": site.vote_url_template,
        }
        for site in SUPPORTED_SITES.values()
    ]


def build_vote_url(site_key: str, project_id: str) -> Optional[str]:
    site = SUPPORTED_SITES.get(site_key)
    if not site or not project_id:
        return None
    return site.build_vote_url(project_id)
