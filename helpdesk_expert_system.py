#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROJET M2-MIAGE - UFHB (Cours d'Intelligence Artificielle - Dr GBAME Gbede Sylvain)
Sujet 1 : Système Expert de Support Informatique (Helpdesk Niveau 1)

Contenu :
 - Frames (cadres) + ontologie, 42 règles de production
 - Incertitude : facteurs de certitude de MYCIN
 - Chaînage avant et chaînage arrière
 - Module d'explication ("Pourquoi cette conclusion ?" / "Pourquoi cette question ?")
 - Outil d'administration de la base de règles (CRUD, cohérence, JSON)
 - Évaluation sur 30 cas + benchmark mesuré face à Scikit-learn
 - Interface CLI et application Flask

Utilisation :
    python helpdesk_expert_system.py          -> évaluation + benchmark
    python helpdesk_expert_system.py --cli    -> mode interactif
    python helpdesk_expert_system.py --web    -> application Flask
"""

import json
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Callable


# ------------------------------------------------------------------------------
# Encodage de la console : sous Windows, sys.stdout utilise cp1252 par défaut et
# lève UnicodeEncodeError sur les caractères semi-graphiques de l'arbre
# d'explication (─, └). On force UTF-8 pour la sortie standard et le terminal.
# ------------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


# ==============================================================================
# 1. ONTOLOGIE ET CADRES (FRAMES)
# ==============================================================================

class Frame:
    """Cadre avec attributs (slots) et héritage de propriétés."""
    def __init__(self, name: str, parent: Optional['Frame'] = None, slots: Optional[Dict] = None):
        self.name = name
        self.parent = parent
        self.slots = slots or {}

    def get_slot(self, slot_name: str):
        if slot_name in self.slots:
            return self.slots[slot_name]
        if self.parent is not None:
            return self.parent.get_slot(slot_name)
        return None

    def to_dict(self) -> Dict:
        inherited = self.parent.to_dict() if self.parent else {}
        inherited.update(self.slots)
        return inherited


def build_domain_ontology() -> Dict[str, Frame]:
    actif_it = Frame("Actif_IT", slots={
        "niveau_support_defaut": "Niveau 1", "sla_heures": 4, "droits_admin_requis": False,
        "escalade_cible": "Support Niveau 2 - Techniciens Proximité"})
    return {
        "Actif_IT": actif_it,
        "Réseau": Frame("Réseau", actif_it, {
            "sla_heures": 2, "protocoles": ["Ethernet", "Wi-Fi", "DHCP", "DNS", "VPN IPsec/SSL"],
            "escalade_cible": "Équipe Réseau & Télécoms (N2)"}),
        "Impression": Frame("Impression", actif_it, {
            "sla_heures": 8, "composants": ["Spouleur", "Toner", "Tambour", "Bac Papier", "Port TCP/9100"],
            "escalade_cible": "Maintenance Matérielle & Reprographie (N2)"}),
        "Messagerie": Frame("Messagerie", actif_it, {
            "sla_heures": 4, "composants": ["Client Outlook", "Fichier OST/PST", "Serveur Exchange/SMTP", "Antispam"],
            "escalade_cible": "Administrateurs Messagerie & Collaboration (N2)"}),
        "Sécurité/AD": Frame("Sécurité/AD", actif_it, {
            "sla_heures": 1, "droits_admin_requis": True,
            "composants": ["Active Directory", "GPO", "MFA/2FA", "Gestionnaire d'identifiants"],
            "escalade_cible": "Administrateurs Systèmes & IAM (N2)"}),
        "Poste/OS": Frame("Poste/OS", actif_it, {
            "sla_heures": 4, "composants": ["Disque C:", "RAM", "Pilotes", "Périphériques USB/Vidéo"],
            "escalade_cible": "Support Proximité Poste de Travail (N2)"}),
        "Applicatif": Frame("Applicatif", actif_it, {
            "sla_heures": 2, "droits_admin_requis": True,
            "composants": ["Serveur ERP", "Base de données", "Habilitations", "Macros Office"],
            "escalade_cible": "Équipe Études & Applications Métier / MOA (N2)"}),
    }


# ==============================================================================
# 2. RÈGLES ET FAITS AVEC FACTEURS DE CERTITUDE
# ==============================================================================

@dataclass
class Rule:
    id: str
    category: str
    premises: List[str]
    conclusion: str
    cf: float
    is_diagnostic: bool
    description: str
    resolution: str = ""


@dataclass
class FactTrace:
    name: str
    cf: float
    sources: List[str] = field(default_factory=list)


QUESTIONS_SYMPTOMES: Dict[str, str] = {
    "icone_reseau_croix_rouge": "L'icône réseau affiche-t-elle une croix rouge ou un globe barré ?",
    "cable_ethernet_utilise": "Utilisez-vous une connexion par câble Ethernet (RJ45) ?",
    "led_port_rj45_eteinte": "Les voyants lumineux (LED) sur le port RJ45 du PC sont-ils éteints ?",
    "wifi_utilise": "Essayez-vous de vous connecter en Wi-Fi ?",
    "aucun_reseau_wifi_visible": "La liste des réseaux Wi-Fi disponibles est-elle totalement vide ?",
    "wifi_connecte": "Le PC est-il bien connecté au réseau Wi-Fi de l'organisation ?",
    "icone_triangle_jaune": "Y a-t-il un triangle jaune ou la mention 'Connecté, pas d'Internet' ?",
    "adresse_ip_169_254": "La commande 'ipconfig' affiche-t-elle une adresse IP commençant par 169.254.x.x ?",
    "message_conflit_ip": "Un message système indique-t-il un conflit d'adresse IP sur le réseau ?",
    "ping_passerelle_ok": "Le test de 'ping' vers la passerelle par défaut réussit-il ?",
    "ping_ip_externe_ok": "Le test de 'ping 8.8.8.8' (adresse IP externe) réussit-il ?",
    "site_web_inaccessible_par_nom": "Les sites web sont-ils inaccessibles par leur nom (ex: www.google.com) ?",
    "navigation_web_lente": "La navigation web est-elle anormalement lente ou bloquée par intermittence ?",
    "erreur_407_authentification_requise": "Le navigateur renvoie-t-il une erreur 407 (Proxy Authentication Required) ?",
    "teletravail": "L'utilisateur est-il actuellement à distance (en télétravail) ?",
    "vpn_erreur_connexion": "Le client VPN affiche-t-il un échec lors de la tentative de connexion ?",
    "certificat_vpn_expire": "Le journal VPN mentionne-t-il une erreur de certificat expiré ou invalide ?",
    "vpn_connecte": "Le tunnel VPN est-il indiqué comme 'Connecté' ?",
    "lecteur_reseau_inaccessible": "Les lecteurs réseau partagés (ex: Z:) sont-ils inaccessibles malgré le VPN ?",
    "imprimante_allumee": "L'imprimante est-elle bien sous tension (écran ou voyant allumé) ?",
    "voyant_erreur_clignote": "Un voyant orange/rouge clignote-t-il sur le panneau de l'imprimante ?",
    "pas_de_voyant_erreur": "L'imprimante n'affiche-t-elle aucun voyant d'erreur sur son boîtier ?",
    "document_bloque_file": "Les documents restent-ils bloqués dans la file d'attente Windows ?",
    "code_bourrage_papier": "L'écran de l'imprimante indique-t-il un bourrage papier (Paper Jam) ?",
    "message_toner_vide": "L'imprimante affiche-t-elle 'Toner vide' ou 'Remplacer cartouche' ?",
    "impression_pages_blanches_ou_stries": "Les feuilles sortent-elles blanches, très pâles ou avec des bandes noires ?",
    "toner_non_vide": "La cartouche de toner a-t-elle été vérifiée comme n'étant pas vide ?",
    "tous_documents_bloques_file": "Est-il impossible d'annuler ou de purger les travaux dans la file d'impression ?",
    "imprimante_reseau_statut_hors_ligne": "L'imprimante réseau apparaît-elle avec le statut 'Hors connexion' sur le PC ?",
    "ping_imprimante_ko": "Le ping vers l'adresse IP de l'imprimante échoue-t-il (Délai d'attente dépassé) ?",
    "impression_caracteres_incoherents": "L'imprimante sort-elle des dizaines de pages couvertes de symboles bizarres ?",
    "outlook_connecte": "Le logiciel de messagerie Outlook démarre-t-il et affiche-t-il 'Connecté' ?",
    "envoi_impossible": "L'envoi de nouveaux courriels est-il bloqué ?",
    "message_boite_pleine": "Recevez-vous une alerte indiquant que votre boîte aux lettres est pleine ?",
    "piece_jointe_volumineuse": "Le message bloqué contient-il une pièce jointe supérieure à 25 Mo ?",
    "outlook_bloque_demarrage": "Outlook reste-t-il figé sur 'Traitement en cours' ou refuse-t-il de s'ouvrir ?",
    "erreur_fichier_ost_pst": "Un message mentionne-t-il que le fichier de données (.OST ou .PST) ne peut être ouvert ?",
    "email_attendu_non_recu": "Un email précis envoyé par un interlocuteur externe est-il introuvable ?",
    "envoi_reception_autres_ok": "Recevez-vous et envoyez-vous normalement vos autres courriels ?",
    "outlook_demande_mot_de_passe_en_boucle": "La fenêtre de mot de passe Outlook réapparaît-elle sans cesse malgré la bonne saisie ?",
    "echec_ouverture_session": "L'ouverture de session Windows ou domaine est-elle refusée ?",
    "message_identifiants_incorrects": "Le système affiche-t-il 'Nom d'utilisateur ou mot de passe incorrect' ?",
    "touche_verr_maj_Ou_clavier_qwerty": "La touche Verr Maj est-elle activée ou le clavier est-il passé en QWERTY/EN ?",
    "message_compte_verrouille": "Le message indique-t-il 'Ce compte est actuellement verrouillé' ?",
    "non_change_depuis_90_jours": "Votre mot de passe n'a-t-il pas été renouvelé depuis plus de 90 jours ?",
    "changement_telephone_recent": "Avez-vous récemment changé ou réinitialisé votre smartphone professionnel ?",
    "code_mfa_non_recu": "La notification de double authentification (MFA/Authenticator) n'arrive-t-elle plus ?",
    "ouverture_session_domaine_impossible": "Le poste refuse-t-il la connexion au domaine de l'entreprise ?",
    "erreur_relation_approbation": "Le message indique-t-il 'La relation d'approbation entre cette station et le domaine a échoué' ?",
    "pc_tres_lent": "L'ordinateur souffre-t-il de ralentissements extrêmes au quotidien ?",
    "ventilateur_bruyant": "Le ventilateur du processeur tourne-t-il à plein régime de façon continue ?",
    "alerte_espace_disque_faible": "Windows affiche-t-il une notification d'espace disque faible sur le lecteur C: ?",
    "utilisation_ram_sup_90": "Le Gestionnaire des tâches indique-t-il une mémoire RAM utilisée à plus de 90 % ?",
    "pc_s_allume": "L'unité centrale s'allume-t-elle (voyants et ventilateurs actifs) ?",
    "ecran_noir": "Le moniteur reste-t-il totalement noir ?",
    "voyant_ecran_orange_veille": "Le voyant du moniteur est-il orange (en veille) avec mention 'No Signal' ?",
    "ecran_bleu_bsod": "L'ordinateur redémarre-t-il brutalement avec un écran bleu (BSOD) ?",
    "installation_pilote_ou_maj_recente": "Un nouveau périphérique, pilote ou mise à jour système a-t-il été installé récemment ?",
    "peripherique_usb_non_reconnu": "Votre clé USB, souris ou casque USB n'est-il pas détecté sur le port actuel ?",
    "fonctionne_sur_autre_port": "Ce même périphérique USB fonctionne-t-il lorsqu'on le branche sur un autre port ?",
    "application_metier_inaccessible": "L'application métier (ERP / Intranet) refuse-t-elle de s'ouvrir ?",
    "erreur_http_500_ou_503": "Le navigateur ou client lourd affiche-t-il une erreur serveur 500, 502 ou 503 ?",
    "erreur_acces_refuse_module_erp": "Avez-vous un message 'Accès refusé / Droits insuffisants' sur un module de l'ERP ?",
    "nouveau_poste_ou_mutation": "Venez-vous de prendre un nouveau poste ou de changer de service ?",
    "macro_ou_export_excel_bloque": "Les boutons ou macros d'un fichier Excel métier refusent-ils de s'exécuter ?",
    "alerte_securite_office": "Un bandeau rouge/jaune Microsoft Office indique-t-il que les macros ont été désactivées ?",
}


def build_knowledge_base() -> List[Rule]:
    """42 règles : R01-R10 intermédiaires, R11-R42 diagnostics finaux."""
    return [
        # --- Intermédiaires ---
        Rule("R01", "Réseau", ["icone_reseau_croix_rouge", "cable_ethernet_utilise"],
             "defaut_liaison_physique", 0.90, False,
             "Défaut de liaison physique Ethernet détecté (Couche 1 OSI)"),
        Rule("R02", "Réseau", ["wifi_connecte", "icone_triangle_jaune"],
             "reseau_local_sans_internet", 0.85, False,
             "Connexion Wi-Fi locale établie mais absence de routage IP/Internet"),
        Rule("R03", "Réseau", ["ping_passerelle_ok", "ping_ip_externe_ok"],
             "connectivite_ip_externe_ok", 0.95, False,
             "Connectivité IP et routage externe opérationnels (Couche 3 OSI OK)"),
        Rule("R04", "Impression", ["imprimante_allumee", "voyant_erreur_clignote"],
             "alerte_materielle_imprimante", 0.90, False,
             "Alerte matérielle ou consommable signalée par l'imprimante"),
        Rule("R05", "Impression", ["imprimante_allumee", "pas_de_voyant_erreur", "document_bloque_file"],
             "probleme_logiciel_impression", 0.85, False,
             "Dysfonctionnement logiciel du sous-système d'impression"),
        Rule("R06", "Messagerie", ["outlook_connecte", "envoi_impossible"],
             "anomalie_sortante_messagerie", 0.85, False,
             "Anomalie lors de l'émission de courriels (flux sortant bloqué)"),
        Rule("R07", "Sécurité/AD", ["echec_ouverture_session", "message_identifiants_incorrects"],
             "probleme_authentification_utilisateur", 0.85, False,
             "Rejet d'authentification par le contrôleur de domaine"),
        Rule("R08", "Poste/OS", ["pc_tres_lent", "ventilateur_bruyant"],
             "surcharge_ressources_systeme", 0.80, False,
             "Saturation des ressources matérielles du poste de travail"),
        Rule("R09", "Poste/OS", ["pc_s_allume", "ecran_noir"],
             "defaut_affichage_ou_boot", 0.85, False,
             "Unité centrale sous tension mais absence de signal vidéo"),
        Rule("R10", "Applicatif", ["connectivite_ip_externe_ok", "application_metier_inaccessible"],
             "incident_couche_applicative", 0.90, False,
             "Réseau fonctionnel mais indisponibilité de la couche applicative métier"),

        # --- Diagnostics : Réseau ---
        Rule("R11", "Réseau", ["defaut_liaison_physique", "led_port_rj45_eteinte"],
             "diag_cable_rj45_debranche_ou_hs", 0.95, True,
             "Câble réseau Ethernet (RJ45) débranché, endommagé ou prise murale non brassée",
             "1. Vérifier l'insertion du câble RJ45 côté PC et côté prise murale (clic audible).\n"
             "2. Tester avec un cordon Ethernet neuf certifié Cat6.\n"
             "3. Si les LED restent éteintes, relever le numéro du bandeau mural et escalader au N2 Réseau pour vérifier le port du switch."),
        Rule("R12", "Réseau", ["icone_reseau_croix_rouge", "wifi_utilise", "aucun_reseau_wifi_visible"],
             "diag_carte_wifi_desactivee", 0.90, True,
             "Carte Wi-Fi désactivée (Mode Avion actif ou interrupteur matériel coupé)",
             "1. Vérifier dans la barre des tâches Windows que le 'Mode Avion' est désactivé.\n"
             "2. Appuyer sur la touche fonction Wi-Fi du clavier (souvent Fn + F2/F12).\n"
             "3. Ouvrir 'ncpa.cpl', faire un clic droit sur la carte Wi-Fi et sélectionner 'Activer'."),
        Rule("R13", "Réseau", ["reseau_local_sans_internet", "adresse_ip_169_254"],
             "diag_echec_serveur_dhcp", 0.95, True,
             "Absence d'attribution d'adresse IP par le serveur DHCP (Adresse APIPA 169.254.x.x)",
             "1. Ouvrir l'invite de commandes (cmd) et exécuter : ipconfig /release puis ipconfig /renew.\n"
             "2. Vérifier l'état du service 'Client DHCP' dans services.msc.\n"
             "3. Si plusieurs postes du même étage sont touchés, escalader au N2 Réseau (pool DHCP saturé)."),
        Rule("R14", "Réseau", ["reseau_local_sans_internet", "message_conflit_ip"],
             "diag_conflit_adresse_ip", 0.95, True,
             "Conflit d'adresse IP statique avec un autre équipement sur le sous-réseau",
             "1. Ouvrir les propriétés IPv4 de la carte réseau (ncpa.cpl).\n"
             "2. Passer la configuration de 'IP fixe' vers 'Obtenir une adresse IP automatiquement (DHCP)'.\n"
             "3. Exécuter 'arp -a' pour identifier l'adresse MAC de l'équipement en conflit si une IP fixe est requise."),
        Rule("R15", "Réseau", ["connectivite_ip_externe_ok", "site_web_inaccessible_par_nom"],
             "diag_panne_resolution_dns", 0.92, True,
             "Défaillance de la résolution de noms DNS (Serveur DNS injoignable ou cache corrompu)",
             "1. Ouvrir cmd et vider le cache DNS via la commande : ipconfig /flushdns.\n"
             "2. Tester la résolution avec : nslookup intranet.entreprise.ci.\n"
             "3. Vérifier que les serveurs DNS configurés sur la carte réseau pointent bien vers les contrôleurs de domaine internes."),
        Rule("R16", "Réseau", ["navigation_web_lente", "erreur_407_authentification_requise"],
             "diag_proxy_entreprise_mal_configure", 0.90, True,
             "Échec d'authentification ou mauvaise configuration du serveur Proxy d'entreprise",
             "1. Ouvrir les Options Internet > Onglet Connexions > Paramètres réseau (LAN).\n"
             "2. Cocher 'Détecter automatiquement les paramètres de connexion (WPAD)'.\n"
             "3. Purger les anciens identifiants proxy dans le Gestionnaire d'identification Windows."),
        Rule("R17", "Réseau", ["teletravail", "vpn_erreur_connexion", "certificat_vpn_expire"],
             "diag_certificat_vpn_expire", 0.95, True,
             "Certificat numérique utilisateur ou machine expiré pour l'accès VPN",
             "1. Ouvrir la console 'certmgr.msc' > Personnel > Certificats et vérifier la date d'expiration.\n"
             "2. Générer un nouveau certificat via le portail PKI interne ou demander un renouvellement au N2 Sécurité."),
        Rule("R18", "Réseau", ["teletravail", "vpn_connecte", "lecteur_reseau_inaccessible"],
             "diag_tunnel_vpn_split_dns_incomplet", 0.82, True,
             "Routage VPN partiel (Split-Tunneling) ou lecteur réseau non reconnecté",
             "1. Tester l'accès au serveur de fichiers par son adresse IP directe : \\\\10.x.x.x\\partage.\n"
             "2. Exécuter 'net use * /delete' puis remapper le lecteur via le script de connexion.\n"
             "3. Déconnecter et reconnecter le client VPN en profil 'Full Tunnel'."),

        # --- Diagnostics : Impression ---
        Rule("R19", "Impression", ["alerte_materielle_imprimante", "code_bourrage_papier"],
             "diag_bourrage_papier_imprimante", 0.98, True,
             "Bourrage papier mécanique dans le chemin d'entraînement ou l'unité recto-verso",
             "1. Ouvrir le capot avant et le module recto-verso à l'arrière de l'imprimante.\n"
             "2. Retirer délicatement la feuille bloquée dans le sens de marche sans la déchirer.\n"
             "3. Vérifier l'alignement des guides du bac papier et refermer le capot pour relancer le cycle."),
        Rule("R20", "Impression", ["alerte_materielle_imprimante", "message_toner_vide"],
             "diag_cartouche_toner_epuisee", 0.98, True,
             "Cartouche de toner épuisée nécessitant un remplacement",
             "1. Identifier la référence exacte de l'imprimante et de la cartouche (Noir/Cyan/Magenta/Jaune).\n"
             "2. Remplacer la cartouche par une neuve après avoir retiré le ruban de scellement.\n"
             "3. Imprimer une page de test de configuration."),
        Rule("R21", "Impression", ["impression_pages_blanches_ou_stries", "toner_non_vide"],
             "diag_tambour_ou_tete_impression_encrassee", 0.85, True,
             "Tambour d'imagerie (Drum) usé ou têtes d'impression encrassées",
             "1. Lancer l'utilitaire de nettoyage des têtes / calibration depuis le menu Maintenance de l'imprimante.\n"
             "2. Nettoyer le fil corona du tambour à l'aide de la languette verte.\n"
             "3. Si les stries persistent, remplacer l'unité d'imagerie (Tambour)."),
        Rule("R22", "Impression", ["probleme_logiciel_impression", "tous_documents_bloques_file"],
             "diag_service_spouleur_windows_plante", 0.92, True,
             "Blocage du service Spouleur d'impression Windows (fichiers .SPL/.SHD corrompus)",
             "1. Ouvrir cmd en tant qu'administrateur et taper : net stop spooler.\n"
             "2. Supprimer tous les fichiers présents dans C:\\Windows\\System32\\spool\\PRINTERS.\n"
             "3. Redémarrer le service avec : net start spooler."),
        Rule("R23", "Impression", ["imprimante_reseau_statut_hors_ligne", "ping_imprimante_ko"],
             "diag_imprimante_reseau_deconnectee_ou_ip_changee", 0.90, True,
             "Imprimante réseau injoignable (Câble débranché ou changement d'adresse IP)",
             "1. Imprimer la page de configuration réseau directement depuis le panneau de l'imprimante.\n"
             "2. Vérifier l'adresse IP actuelle et la comparer avec le port TCP/IP configuré sur le PC.\n"
             "3. Décocher l'option 'Utiliser l'imprimante hors connexion' et fixer une réservation DHCP."),
        Rule("R24", "Impression", ["impression_caracteres_incoherents"],
             "diag_pilote_imprimante_inadequat_corrompu", 0.90, True,
             "Pilote d'impression (Driver PCL/PostScript) corrompu ou incompatible avec le modèle",
             "1. Annuler immédiatement la tâche d'impression en cours et éteindre/rallumer l'imprimante pour vider sa mémoire tampon.\n"
             "2. Désinstaller le pilote actuel via 'printui /s /t2'.\n"
             "3. Installer le pilote officiel PCL6 spécifique au modèle de l'imprimante."),

        # --- Diagnostics : Messagerie ---
        Rule("R25", "Messagerie", ["anomalie_sortante_messagerie", "message_boite_pleine"],
             "diag_quota_boite_aux_lettres_depasse", 0.96, True,
             "Dépassement du quota de stockage de la boîte aux lettres Exchange/M365",
             "1. Vider le dossier 'Éléments supprimés' et 'Courrier indésirable' dans Outlook ou Webmail (OWA).\n"
             "2. Trier les messages par taille (> 10 Mo) et archiver les anciens courriels dans une archive en ligne.\n"
             "3. Si le besoin métier est justifié, escalader au N2 Messagerie pour augmenter le quota."),
        Rule("R26", "Messagerie", ["anomalie_sortante_messagerie", "piece_jointe_volumineuse"],
             "diag_taille_piece_jointe_excessive", 0.92, True,
             "Blocage du courriel dans la boîte d'envoi car la pièce jointe dépasse la limite (25 Mo)",
             "1. Passer Outlook en mode 'Travailler hors connexion' pour pouvoir supprimer le mail bloqué dans 'Boîte d'envoi'.\n"
             "2. Repasser en mode connecté.\n"
             "3. Compresser le fichier en .ZIP ou partager un lien sécurisé OneDrive/SharePoint interne."),
        Rule("R27", "Messagerie", ["outlook_bloque_demarrage", "erreur_fichier_ost_pst"],
             "diag_fichier_donnees_outlook_ost_corrompu", 0.94, True,
             "Corruption du fichier de cache local Outlook (.OST) ou d'archive (.PST)",
             "1. Fermer complètement Outlook via le Gestionnaire des tâches.\n"
             "2. Pour un fichier .PST : exécuter l'outil de réparation 'SCANPST.EXE'.\n"
             "3. Pour un fichier .OST : renommer le fichier dans %localappdata%\\Microsoft\\Outlook en .ost.old et relancer Outlook pour recréer le cache."),
        Rule("R28", "Messagerie", ["email_attendu_non_recu", "envoi_reception_autres_ok"],
             "diag_email_bloque_quarantaine_antispam", 0.80, True,
             "Courriel légitime retenu en quarantaine par la passerelle Antispam ou filtré par une règle",
             "1. Vérifier le dossier 'Courrier indésirable' (Junk) et l'onglet 'Autres' d'Outlook.\n"
             "2. Vérifier qu'aucune règle de transfert/suppression automatique n'est active dans Fichier > Gérer les règles.\n"
             "3. Consulter le portail de quarantaine Antispam et libérer l'email si l'expéditeur est fiable."),
        Rule("R29", "Messagerie", ["outlook_demande_mot_de_passe_en_boucle"],
             "diag_jeton_oauth_gestionnaire_identifiants_corrompu", 0.88, True,
             "Corruption du jeton d'authentification moderne (OAuth) dans le Gestionnaire d'identification Windows",
             "1. Fermer toutes les applications Microsoft Office.\n"
             "2. Ouvrir le 'Gestionnaire d'identification' Windows > Informations d'identification Windows.\n"
             "3. Supprimer toutes les entrées 'MicrosoftOffice16_Data' ou 'MS.Outlook', puis relancer Outlook et saisir le mot de passe."),

        # --- Diagnostics : Sécurité / Active Directory ---
        Rule("R30", "Sécurité/AD", ["probleme_authentification_utilisateur", "touche_verr_maj_Ou_clavier_qwerty"],
             "diag_erreur_saisie_clavier_verrmaj", 0.90, True,
             "Erreur de saisie du mot de passe due à Verr Maj (Caps Lock), Verr Num ou bascule clavier AZERTY/QWERTY",
             "1. Vérifier l'état des voyants Verr Maj (Caps Lock) et Verr Num (Pavé numérique).\n"
             "2. Vérifier en bas à droite de l'écran de connexion que la disposition clavier est bien 'FRA (AZERTY)'.\n"
             "3. Cliquer sur l'icône 'œil' dans le champ de saisie pour visualiser les caractères tapés avant que le compte ne se verrouille."),
        Rule("R31", "Sécurité/AD", ["echec_ouverture_session", "message_compte_verrouille"],
             "diag_compte_active_directory_verrouille", 0.98, True,
             "Compte Active Directory verrouillé suite à 5 tentatives de connexion infructueuses",
             "1. Vérifier l'identité de l'appelant selon la procédure de sécurité du Helpdesk.\n"
             "2. Ouvrir la console 'Utilisateurs et ordinateurs Active Directory' (dsa.msc), rechercher l'utilisateur, onglet Compte > Cocher 'Déverrouiller le compte'.\n"
             "3. Si le compte se reverrouille immédiatement, déconnecter les anciens téléphones/sessions RDP mémorisant l'ancien mot de passe."),
        Rule("R32", "Sécurité/AD", ["probleme_authentification_utilisateur", "non_change_depuis_90_jours"],
             "diag_mot_de_passe_domaine_expire", 0.90, True,
             "Expiration de la durée de vie maximale du mot de passe domaine (politique des 90 jours)",
             "1. Si l'utilisateur est au bureau : effectuer un changement de mot de passe ou cocher 'L'utilisateur doit changer le mot de passe à la prochaine ouverture de session' dans AD.\n"
             "2. Si l'utilisateur est à distance : le guider sur le portail Web de réinitialisation en libre-service (SSPR)."),
        Rule("R33", "Sécurité/AD", ["changement_telephone_recent", "code_mfa_non_recu"],
             "diag_desynchronisation_mfa_double_facteur", 0.95, True,
             "Perte d'inscription de l'application MFA (Authenticator) suite à un changement de smartphone",
             "1. Vérifier formellement l'identité du collaborateur (validation manager ou appel vidéo).\n"
             "2. Dans le portail d'administration IAM/Entra ID, cliquer sur 'Exiger un réenregistrement MFA' (Require re-register MFA).\n"
             "3. Accompagner l'utilisateur dans le scan du nouveau QR Code sur son nouveau téléphone."),
        Rule("R34", "Sécurité/AD", ["ouverture_session_domaine_impossible", "erreur_relation_approbation"],
             "diag_perte_relation_approbation_domaine_ad", 0.95, True,
             "Rupture du canal sécurisé (Relation d'approbation) entre le poste de travail et le domaine Active Directory",
             "1. Débrancher le câble réseau (et couper le Wi-Fi) pour ouvrir la session avec les identifiants mis en cache, ou se connecter avec le compte Administrateur local.\n"
             "2. Rebrancher le réseau, ouvrir PowerShell en administrateur et exécuter : Test-ComputerSecureChannel -Repair -Credential (Get-Credential).\n"
             "3. Redémarrer le poste de travail."),

        # --- Diagnostics : Poste de travail / OS ---
        Rule("R35", "Poste/OS", ["surcharge_ressources_systeme", "alerte_espace_disque_faible"],
             "diag_partition_systeme_c_saturee", 0.94, True,
             "Saturation critique de la partition système C: empêchant le fichier d'échange (Swap) de fonctionner",
             "1. Lancer l'outil 'Nettoyage de disque' (cleanmgr) en mode administrateur et purger les fichiers temporaires Windows Update.\n"
             "2. Vider la Corbeille et le dossier Téléchargements avec l'accord de l'utilisateur.\n"
             "3. Activer les 'Fichiers à la demande' sur OneDrive pour libérer l'espace occupé localement."),
        Rule("R36", "Poste/OS", ["surcharge_ressources_systeme", "utilisation_ram_sup_90"],
             "diag_saturation_memoire_vive_ram", 0.90, True,
             "Saturation de la mémoire vive (RAM) par des processus gourmands ou fuite mémoire",
             "1. Ouvrir le Gestionnaire des tâches (Ctrl+Maj+Échap), trier par colonne 'Mémoire' et fermer les applications non essentielles (ex: dizaines d'onglets navigateur).\n"
             "2. Désactiver les applications superflues dans l'onglet 'Démarrage'.\n"
             "3. Si le poste ne dispose que de 8 Go et utilise des outils lourds, créer une demande de mise à niveau matérielle vers 16 Go."),
        Rule("R37", "Poste/OS", ["defaut_affichage_ou_boot", "voyant_ecran_orange_veille"],
             "diag_cable_video_hdmi_dp_mal_branche", 0.88, True,
             "Câble vidéo (HDMI / DisplayPort / VGA) déconnecté ou mauvaise source d'entrée sélectionnée sur l'écran",
             "1. Vérifier et revisser/enfoncer fermement le câble vidéo derrière le moniteur et derrière l'unité centrale (ou station d'accueil).\n"
             "2. Appuyer sur le bouton 'Input / Source' de l'écran pour sélectionner la bonne entrée (HDMI ou DisplayPort).\n"
             "3. Appuyer sur les touches Windows + P et sélectionner 'Dupliquer' ou 'Étendre'."),
        Rule("R38", "Poste/OS", ["ecran_bleu_bsod", "installation_pilote_ou_maj_recente"],
             "diag_incompatibilite_pilote_bsod", 0.90, True,
             "Plantage noyau Windows (Écran bleu BSOD) causé par un pilote matériel ou une mise à jour incompatible",
             "1. Redémarrer le poste en Mode sans échec (avec prise en charge réseau).\n"
             "2. Ouvrir le Gestionnaire de périphériques (devmgmt.msc), identifier le pilote récemment modifié et cliquer sur 'Restaurer le pilote' (Roll Back Driver).\n"
             "3. Analyser le fichier minidump dans C:\\Windows\\Minidump si le problème persiste et escalader au N2."),
        Rule("R39", "Poste/OS", ["peripherique_usb_non_reconnu", "fonctionne_sur_autre_port"],
             "diag_port_usb_physique_endommage_ou_veille", 0.88, True,
             "Port USB spécifique défectueux ou désactivé par la suspension sélective d'alimentation USB",
             "1. Inspecter physiquement le port USB (broches tordues ou poussière).\n"
             "2. Dans le Gestionnaire de périphériques > Contrôleurs de bus USB > Concentrateur USB racine > Gestion de l'alimentation : décocher 'Autoriser l'ordinateur à éteindre ce périphérique'.\n"
             "3. Utiliser les ports USB directement soudés à la carte mère (à l'arrière du PC)."),

        # --- Diagnostics : Applicatif métier / ERP ---
        Rule("R40", "Applicatif", ["incident_couche_applicative", "erreur_http_500_ou_503"],
             "diag_serveur_application_erp_indisponible", 0.95, True,
             "Panne centrale du serveur d'application ERP ou de sa base de données (Erreur 500/503)",
             "1. Vérifier sur le tableau de bord de supervision (Nagios/Zabbix) si une panne générale est déclarée.\n"
             "2. Créer un ticket d'incident majeur (Priorité P1) et escalader immédiatement à l'équipe Exploitation / Administrateurs ERP (Niveau 2/3).\n"
             "3. Informer l'utilisateur du délai estimé de rétablissement."),
        Rule("R41", "Applicatif", ["erreur_acces_refuse_module_erp", "nouveau_poste_ou_mutation"],
             "diag_habilitation_profil_erp_manquante", 0.92, True,
             "Droits et habilitations applicatives non mis à jour dans l'ERP suite à une prise de poste ou mutation",
             "1. Vérifier le profil actuel de l'utilisateur dans la console de gestion des identités.\n"
             "2. Demander la validation écrite du responsable hiérarchique (Matrice SoD - Séparation des tâches).\n"
             "3. Attribuer le rôle métier correspondant ou transmettre à la MOA ERP."),
        Rule("R42", "Applicatif", ["macro_ou_export_excel_bloque", "alerte_securite_office"],
             "diag_blocage_macros_vba_strategie_securite", 0.90, True,
             "Blocage de sécurité des macros VBA sur un fichier Excel provenant d'un emplacement non approuvé",
             "1. Fermer le fichier Excel, faire un clic droit sur le fichier > Propriétés > Cocher la case 'Débloquer' en bas de l'onglet Général.\n"
             "2. Dans Excel : Fichier > Options > Centre de gestion de la confidentialité > Emplacements approuvés : ajouter le dossier réseau officiel du service.\n"
             "3. Ne jamais activer les macros sur un fichier reçu d'un expéditeur externe inconnu."),
    ]


# ==============================================================================
# 3. MOTEUR D'INFÉRENCE
# ==============================================================================

class HelpdeskInferenceEngine:
    """Chaînage avant / arrière, facteurs de certitude MYCIN, explication."""

    def __init__(self, rules: List[Rule], ontology: Dict[str, Frame], threshold: float = 0.20):
        self.rules = rules
        self.ontology = ontology
        self.threshold = threshold
        self.facts: Dict[str, FactTrace] = {}
        self.fired_rules_history: List[str] = []

    def reset(self):
        self.facts.clear()
        self.fired_rules_history.clear()

    @staticmethod
    def combine_mycin_cf(cf1: float, cf2: float) -> float:
        """Combinaison parallèle de deux certitudes (formule de MYCIN)."""
        if cf1 > 0 and cf2 > 0:
            return round(cf1 + cf2 * (1.0 - cf1), 4)
        if cf1 < 0 and cf2 < 0:
            return round(cf1 + cf2 * (1.0 + cf1), 4)
        denom = 1.0 - min(abs(cf1), abs(cf2))
        return round((cf1 + cf2) / denom, 4) if denom != 0 else 0.0

    def add_fact(self, name: str, cf: float, source: str = "Saisie utilisateur"):
        cf = max(-1.0, min(1.0, float(cf)))
        if name not in self.facts:
            self.facts[name] = FactTrace(name, round(cf, 4), [f"{source} (CF={cf:.2f})"])
        else:
            combined = self.combine_mycin_cf(self.facts[name].cf, cf)
            self.facts[name].cf = combined
            msg = f"{source} (apport CF={cf:.2f} -> CF combiné={combined:.2f})"
            if msg not in self.facts[name].sources:
                self.facts[name].sources.append(msg)

    def get_fact_cf(self, name: str) -> float:
        return self.facts[name].cf if name in self.facts else 0.0

    # ---- Chaînage avant ----
    def forward_chaining(self, initial_facts: Dict[str, float]) -> List[Tuple[Rule, float]]:
        self.reset()
        for name, cf in initial_facts.items():
            self.add_fact(name, cf, source="Observation initiale")

        fired = set()
        changed = True
        while changed:
            changed = False
            for rule in self.rules:
                if rule.id in fired:
                    continue
                min_cf = min((self.get_fact_cf(p) for p in rule.premises), default=0.0)
                if min_cf >= self.threshold:
                    inferred = round(rule.cf * max(0.0, min_cf), 4)
                    src = (f"Règle {rule.id} [{', '.join(rule.premises)}] "
                           f"(CF_prémisse={min_cf:.2f} * CF_règle={rule.cf:.2f})")
                    self.add_fact(rule.conclusion, inferred, source=src)
                    fired.add(rule.id)
                    self.fired_rules_history.append(rule.id)
                    changed = True

        diagnostics, seen = [], set()
        for rule in self.rules:
            if rule.is_diagnostic and rule.conclusion in self.facts:
                cf = self.facts[rule.conclusion].cf
                if cf >= self.threshold and rule.conclusion not in seen:
                    diagnostics.append((rule, cf))
                    seen.add(rule.conclusion)
        diagnostics.sort(key=lambda x: x[1], reverse=True)
        return diagnostics

    # ---- Chaînage arrière ----
    def backward_chaining(self, goal: str, known_facts: Optional[Dict[str, float]] = None,
                          ask_callback: Optional[Callable[[str, Rule], float]] = None) -> float:
        if known_facts is not None:
            self.reset()
            for k, v in known_facts.items():
                self.add_fact(k, v, source="Fait initial")
        return self._prove_goal(goal, set(), None, ask_callback)

    def _prove_goal(self, goal: str, visited: set, current_rule: Optional[Rule],
                    ask_callback: Optional[Callable[[str, Rule], float]]) -> float:
        if goal in self.facts:
            return self.facts[goal].cf
        if goal in visited:
            return 0.0
        visited.add(goal)

        matching = [r for r in self.rules if r.conclusion == goal]
        if matching:
            for rule in matching:
                cfs, viable = [], True
                for premise in rule.premises:
                    p_cf = self._prove_goal(premise, visited.copy(), rule, ask_callback)
                    if p_cf < self.threshold:
                        viable = False
                        break
                    cfs.append(p_cf)
                if viable and cfs:
                    min_cf = min(cfs)
                    inferred = round(rule.cf * min_cf, 4)
                    src = (f"Chaînage arrière via {rule.id} [{', '.join(rule.premises)}] "
                           f"(min_CF={min_cf:.2f} * CF_règle={rule.cf:.2f})")
                    self.add_fact(goal, inferred, source=src)
                    if rule.id not in self.fired_rules_history:
                        self.fired_rules_history.append(rule.id)
            return self.get_fact_cf(goal)

        # Fait primaire : on interroge l'utilisateur
        if ask_callback is not None and current_rule is not None:
            user_cf = ask_callback(goal, current_rule)
            self.add_fact(goal, user_cf, source="Réponse utilisateur interactive")
            return user_cf
        return 0.0

    # ---- Explication ----
    def explain_conclusion(self, conclusion_name: str, indent: int = 0) -> str:
        prefix = "  " * indent
        if conclusion_name not in self.facts:
            return f"{prefix}- Le fait '{conclusion_name}' n'est pas prouvé (CF = 0.0)."
        ft = self.facts[conclusion_name]
        lines = [f"{prefix}* Fait / Conclusion : '{conclusion_name}' [CF = {ft.cf:.2f} ({ft.cf*100:.1f}%)]"]
        for src in ft.sources:
            lines.append(f"{prefix}  └─ Preuve : {src}")
        for rule in self.rules:
            if rule.conclusion == conclusion_name and rule.id in self.fired_rules_history:
                lines.append(f"{prefix}  └─ Détail de la règle {rule.id} ({rule.description}) :")
                for prem in rule.premises:
                    lines.append(self.explain_conclusion(prem, indent + 3))
                if rule.is_diagnostic and rule.category in self.ontology:
                    fi = self.ontology[rule.category].to_dict()
                    lines.append(f"{prefix}  └─ Cadre Ontologique (Frame '{rule.category}') :")
                    lines.append(f"{prefix}     • SLA cible : {fi.get('sla_heures')}h | "
                                 f"Droits admin requis : {fi.get('droits_admin_requis')} | "
                                 f"Escalade : {fi.get('escalade_cible')}")
        return "\n".join(lines)


# ==============================================================================
# 4. OUTIL D'ADMINISTRATION DE LA BASE DE RÈGLES
# ==============================================================================

class RuleBaseAdminTool:
    def __init__(self, rules: List[Rule]):
        self.rules = rules

    def list_rules(self, category: Optional[str] = None) -> List[Rule]:
        if category:
            return [r for r in self.rules if r.category.lower() == category.lower()]
        return self.rules

    def add_rule(self, new_rule: Rule) -> Tuple[bool, str]:
        if any(r.id == new_rule.id for r in self.rules):
            return False, f"Erreur : une règle avec l'identifiant {new_rule.id} existe déjà."
        if not (-1.0 <= new_rule.cf <= 1.0):
            return False, "Erreur : le coefficient de confiance (CF) doit être compris entre -1.0 et 1.0."
        self.rules.append(new_rule)
        return True, f"Règle {new_rule.id} ajoutée ({len(self.rules)} règles au total)."

    def delete_rule(self, rule_id: str) -> Tuple[bool, str]:
        for i, r in enumerate(self.rules):
            if r.id == rule_id:
                del self.rules[i]
                return True, f"Règle {rule_id} supprimée."
        return False, f"Règle {rule_id} introuvable."

    def check_consistency(self) -> Dict[str, List[str]]:
        report = {"doublons_premisses": [], "faits_intermediaires_inutilises": []}
        seen = {}
        inter = {r.conclusion: r.id for r in self.rules if not r.is_diagnostic}
        all_premises = {p for r in self.rules for p in r.premises}
        for r in self.rules:
            key = tuple(sorted(r.premises))
            if key in seen:
                report["doublons_premisses"].append(f"{r.id} a les mêmes prémisses que {seen[key]}")
            else:
                seen[key] = r.id
        for concl, rid in inter.items():
            if concl not in all_premises:
                report["faits_intermediaires_inutilises"].append(
                    f"La conclusion intermédiaire '{concl}' ({rid}) n'est utilisée par aucune règle.")
        return report

    def export_to_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self.rules], f, indent=2, ensure_ascii=False)

    def import_from_json(self, filepath: str):
        with open(filepath, "r", encoding="utf-8") as f:
            self.rules[:] = [Rule(**item) for item in json.load(f)]


# ==============================================================================
# 5. JEU D'ÉVALUATION : 30 CAS
# ==============================================================================

def build_30_test_cases() -> List[Dict]:
    def c(i, desc, facts, expected):
        return {"id": f"CAS_{i:02d}", "desc": desc, "facts": facts, "expected": expected}
    return [
        c(1, "Câble RJ45 débranché au bureau", {"icone_reseau_croix_rouge": 1.0, "cable_ethernet_utilise": 1.0, "led_port_rj45_eteinte": 1.0}, "diag_cable_rj45_debranche_ou_hs"),
        c(2, "Mode avion activé par erreur sur PC portable", {"icone_reseau_croix_rouge": 1.0, "wifi_utilise": 1.0, "aucun_reseau_wifi_visible": 1.0}, "diag_carte_wifi_desactivee"),
        c(3, "Panne serveur DHCP sur le VLAN Wi-Fi (IP 169.254.x.x)", {"wifi_connecte": 1.0, "icone_triangle_jaune": 1.0, "adresse_ip_169_254": 1.0}, "diag_echec_serveur_dhcp"),
        c(4, "Conflit d'adresse IP fixe entre deux postes", {"wifi_connecte": 1.0, "icone_triangle_jaune": 0.9, "message_conflit_ip": 1.0}, "diag_conflit_adresse_ip"),
        c(5, "Serveur DNS muet alors que le ping 8.8.8.8 fonctionne", {"ping_passerelle_ok": 1.0, "ping_ip_externe_ok": 1.0, "site_web_inaccessible_par_nom": 1.0}, "diag_panne_resolution_dns"),
        c(6, "Blocage Proxy avec erreur HTTP 407", {"navigation_web_lente": 0.9, "erreur_407_authentification_requise": 1.0}, "diag_proxy_entreprise_mal_configure"),
        c(7, "Télétravailleur avec certificat VPN expiré", {"teletravail": 1.0, "vpn_erreur_connexion": 1.0, "certificat_vpn_expire": 1.0}, "diag_certificat_vpn_expire"),
        c(8, "Télétravailleur connecté au VPN mais sans accès au lecteur Z:", {"teletravail": 1.0, "vpn_connecte": 1.0, "lecteur_reseau_inaccessible": 0.95}, "diag_tunnel_vpn_split_dns_incomplet"),
        c(9, "Bourrage papier dans le bac d'impression", {"imprimante_allumee": 1.0, "voyant_erreur_clignote": 1.0, "code_bourrage_papier": 1.0}, "diag_bourrage_papier_imprimante"),
        c(10, "Toner noir épuisé (comptabilité)", {"imprimante_allumee": 1.0, "voyant_erreur_clignote": 1.0, "message_toner_vide": 1.0}, "diag_cartouche_toner_epuisee"),
        c(11, "Traces noires malgré toner neuf", {"impression_pages_blanches_ou_stries": 0.9, "toner_non_vide": 1.0}, "diag_tambour_ou_tete_impression_encrassee"),
        c(12, "Spouleur Windows figé, 12 documents bloqués", {"imprimante_allumee": 1.0, "pas_de_voyant_erreur": 1.0, "document_bloque_file": 1.0, "tous_documents_bloques_file": 1.0}, "diag_service_spouleur_windows_plante"),
        c(13, "Imprimante réseau hors ligne, ping KO", {"imprimante_reseau_statut_hors_ligne": 1.0, "ping_imprimante_ko": 1.0}, "diag_imprimante_reseau_deconnectee_ou_ip_changee"),
        c(14, "Caractères hiéroglyphiques après changement de PC", {"impression_caracteres_incoherents": 1.0}, "diag_pilote_imprimante_inadequat_corrompu"),
        c(15, "Boîte aux lettres Outlook saturée", {"outlook_connecte": 1.0, "envoi_impossible": 1.0, "message_boite_pleine": 1.0}, "diag_quota_boite_aux_lettres_depasse"),
        c(16, "Mail bloqué avec vidéo de 45 Mo", {"outlook_connecte": 1.0, "envoi_impossible": 1.0, "piece_jointe_volumineuse": 1.0}, "diag_taille_piece_jointe_excessive"),
        c(17, "Outlook plante au lancement (erreur .OST)", {"outlook_bloque_demarrage": 1.0, "erreur_fichier_ost_pst": 1.0}, "diag_fichier_donnees_outlook_ost_corrompu"),
        c(18, "Facture fournisseur non reçue, messagerie OK", {"email_attendu_non_recu": 0.9, "envoi_reception_autres_ok": 1.0}, "diag_email_bloque_quarantaine_antispam"),
        c(19, "Fenêtre d'authentification Outlook en boucle", {"outlook_demande_mot_de_passe_en_boucle": 1.0}, "diag_jeton_oauth_gestionnaire_identifiants_corrompu"),
        c(20, "Mot de passe refusé : Verr Maj enclenchée", {"echec_ouverture_session": 1.0, "message_identifiants_incorrects": 1.0, "touche_verr_maj_Ou_clavier_qwerty": 0.9}, "diag_erreur_saisie_clavier_verrmaj"),
        c(21, "Compte AD verrouillé après 5 essais", {"echec_ouverture_session": 1.0, "message_compte_verrouille": 1.0}, "diag_compte_active_directory_verrouille"),
        c(22, "Mot de passe expiré au retour de congés", {"echec_ouverture_session": 1.0, "message_identifiants_incorrects": 1.0, "non_change_depuis_90_jours": 1.0}, "diag_mot_de_passe_domaine_expire"),
        c(23, "MFA perdu après remplacement d'iPhone", {"changement_telephone_recent": 1.0, "code_mfa_non_recu": 1.0}, "diag_desynchronisation_mfa_double_facteur"),
        c(24, "Erreur de relation d'approbation PC / domaine", {"ouverture_session_domaine_impossible": 1.0, "erreur_relation_approbation": 1.0}, "diag_perte_relation_approbation_domaine_ad"),
        c(25, "PC très lent, disque C: plein à 99 %", {"pc_tres_lent": 1.0, "ventilateur_bruyant": 0.9, "alerte_espace_disque_faible": 1.0}, "diag_partition_systeme_c_saturee"),
        c(26, "PC lent, RAM saturée par 40 onglets", {"pc_tres_lent": 1.0, "ventilateur_bruyant": 0.85, "utilisation_ram_sup_90": 0.95}, "diag_saturation_memoire_vive_ram"),
        c(27, "Écran noir, PC allumé (câble HDMI débranché)", {"pc_s_allume": 1.0, "ecran_noir": 1.0, "voyant_ecran_orange_veille": 0.9}, "diag_cable_video_hdmi_dp_mal_branche"),
        c(28, "Écran bleu après mise à jour de pilote graphique", {"ecran_bleu_bsod": 1.0, "installation_pilote_ou_maj_recente": 0.95}, "diag_incompatibilite_pilote_bsod"),
        c(29, "ERP en erreur HTTP 503, réseau OK", {"ping_passerelle_ok": 1.0, "ping_ip_externe_ok": 1.0, "application_metier_inaccessible": 1.0, "erreur_http_500_ou_503": 1.0}, "diag_serveur_application_erp_indisponible"),
        c(30, "Hors périmètre N1 : odeur de brûlé à l'alimentation", {"odeur_brule_alimentation": 1.0}, "AUCUN_DIAGNOSTIC_ESCALADE_N2"),
    ]


def evaluate_30_cases(engine: HelpdeskInferenceEngine) -> Tuple[List[Dict], int]:
    """Exécute les 30 cas et retourne (lignes de résultats, nombre de réussites)."""
    rows, correct = [], 0
    for tc in build_30_test_cases():
        res = engine.forward_chaining(tc["facts"])
        pred = res[0][0].conclusion if res else "AUCUN_DIAGNOSTIC_ESCALADE_N2"
        cf = res[0][1] if res else 0.0
        ok = pred == tc["expected"]
        correct += ok
        rows.append({"id": tc["id"], "desc": tc["desc"], "expected": tc["expected"],
                     "pred": pred, "cf": cf, "ok": ok})
    return rows, correct


# ==============================================================================
# 6. BENCHMARK MESURÉ : SYSTÈME EXPERT vs SCIKIT-LEARN SUR DONNÉES BRUITÉES
# ==============================================================================

def _expand_primary(premises: List[str], inter_map: Dict[str, List[str]]) -> List[str]:
    """Déplie récursivement les faits intermédiaires jusqu'aux symptômes primaires."""
    out: List[str] = []
    for p in premises:
        out.extend(_expand_primary(inter_map[p], inter_map) if p in inter_map else [p])
    return out


def run_noise_benchmark(rules: List[Rule], seeds=range(10), omit: float = 0.10,
                        noise: float = 0.15, tickets_per_class: int = 10) -> Dict[str, Tuple[float, float, float]]:
    """
    Génère des tickets simulés (omission de symptômes + symptôme parasite) et compare
    le système expert (mesuré, pas écrit en dur) à LinearSVC, RandomForest et KNN.
    Retourne {modèle: (moyenne %, min %, max %)} sur plusieurs tirages.
    ATTENTION : les tickets sont fabriqués à partir des règles -> test circulaire,
    à présenter comme une étude de sensibilité au bruit, pas comme une validation.
    """
    import numpy as np
    from sklearn.svm import LinearSVC
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.model_selection import train_test_split

    inter_map = {r.conclusion: r.premises for r in rules if not r.is_diagnostic}
    derived = {r.conclusion for r in rules}
    symptoms = sorted({p for r in rules for p in r.premises} - derived)
    index = {s: i for i, s in enumerate(symptoms)}
    diag_rules = [r for r in rules if r.is_diagnostic]
    engine = HelpdeskInferenceEngine(rules, build_domain_ontology())
    scores: Dict[str, List[float]] = {"Système expert": [], "LinearSVC": [],
                                      "Random Forest": [], "KNN (k=5)": []}

    for seed in seeds:
        rng = np.random.default_rng(seed)
        X, y = [], []
        for r in diag_rules:
            prim = _expand_primary(r.premises, inter_map)
            for _ in range(tickets_per_class):
                v = np.zeros(len(symptoms))
                for s in prim:
                    v[index[s]] = 1.0 if rng.random() > omit else 0.0
                if rng.random() < noise:
                    v[rng.integers(0, len(symptoms))] = 1.0
                X.append(v)
                y.append(r.conclusion)
        X, y = np.array(X), np.array(y)
        idx_tr, idx_te = train_test_split(np.arange(len(y)), test_size=0.30, random_state=0, stratify=y)

        ok = 0
        for k in idx_te:
            res = engine.forward_chaining({symptoms[j]: 1.0 for j in np.where(X[k] > 0)[0]})
            ok += (res[0][0].conclusion == y[k]) if res else 0
        scores["Système expert"].append(100.0 * ok / len(idx_te))

        models = {"LinearSVC": LinearSVC(C=10, max_iter=10000),
                  "Random Forest": RandomForestClassifier(n_estimators=100, random_state=0),
                  "KNN (k=5)": KNeighborsClassifier(n_neighbors=5)}
        for name, m in models.items():
            scores[name].append(100.0 * m.fit(X[idx_tr], y[idx_tr]).score(X[idx_te], y[idx_te]))

    return {k: (float(np.mean(v)), float(np.min(v)), float(np.max(v))) for k, v in scores.items()}


def evaluate_expert_system_and_compare_ml():
    ontology = build_domain_ontology()
    rules = build_knowledge_base()
    engine = HelpdeskInferenceEngine(rules, ontology)

    print("=" * 100)
    print("ÉVALUATION DU SYSTÈME EXPERT SUR LES 30 CAS D'INCIDENTS HELPDESK N1")
    print("=" * 100)
    print(f"{'ID':<8} | {'Attendu':<46} | {'Prédit':<46} | {'CF':<6} | Statut")
    print("-" * 120)
    rows, correct = evaluate_30_cases(engine)
    for r in rows:
        print(f"{r['id']:<8} | {r['expected'][:46]:<46} | {r['pred'][:46]:<46} | {r['cf']:<6.2f} | "
              f"{'OK' if r['ok'] else 'ERREUR'}")
    print("-" * 120)
    print(f"Précision du système expert : {correct}/{len(rows)} ({100*correct/len(rows):.1f}%)")
    print("Rappel : ces 30 cas sont écrits avec les règles -> cohérence interne, pas validation externe.")

    print("\n" + "=" * 100)
    print("DÉMONSTRATION DE L'EXPLICATION (CAS_29 : chaînage multi-niveaux)")
    print("=" * 100)
    res = engine.forward_chaining(build_30_test_cases()[28]["facts"])
    top_rule, top_cf = res[0]
    print(f"Diagnostic retenu : {top_rule.description} (CF = {top_cf:.2f})\n")
    print("[Pourquoi cette conclusion ?]")
    print(engine.explain_conclusion(top_rule.conclusion))
    print("\n[Procédure de résolution]")
    print(top_rule.resolution)

    try:
        print("\n" + "=" * 100)
        print("BENCHMARK SUR TICKETS BRUITÉS (10 % d'omission, 15 % de symptôme parasite, 10 tirages)")
        print("=" * 100)
        for name, (mean, lo, hi) in run_noise_benchmark(rules).items():
            print(f"• {name:<16} -> {mean:5.1f} %  (min {lo:.1f} %, max {hi:.1f} %)")
        print("Tickets fabriqués à partir des règles : test circulaire, à présenter comme "
              "une étude de sensibilité au bruit.")
    except ImportError:
        print("\n[Installez scikit-learn et numpy pour le benchmark : pip install scikit-learn numpy]")


# ==============================================================================
# 7. INTERFACES : CLI ET FLASK
# ==============================================================================

def interactive_cli():
    ontology = build_domain_ontology()
    rules = build_knowledge_base()
    engine = HelpdeskInferenceEngine(rules, ontology)

    print("\n" + "=" * 75)
    print("ASSISTANT SYSTÈME EXPERT HELPDESK NIVEAU 1 (MODE INTERACTIF)")
    print("=" * 75)
    categories = sorted({r.category for r in rules if r.is_diagnostic})
    for i, cat in enumerate(categories, 1):
        print(f"  {i}. {cat}")
    choice = input(f"\nChoisissez la catégorie (1-{len(categories)}) : ").strip()
    try:
        selected = categories[int(choice) - 1]
    except (ValueError, IndexError):
        selected = "Réseau"

    print(f"\n--- Diagnostic : {selected} ---")
    print("(o = Oui, n = Non, p = Peut-être [CF=0.6], why = Pourquoi cette question ?)\n")
    asked: Dict[str, float] = {}

    def ask(fact_name: str, current_rule: Rule) -> float:
        if fact_name in asked:
            return asked[fact_name]
        q = QUESTIONS_SYMPTOMES.get(fact_name, f"Observez-vous le fait '{fact_name}' ?")
        while True:
            ans = input(f"? {q} [o/n/p/why] : ").strip().lower()
            if ans == "why":
                print(f"   [Explication] Je vérifie la règle {current_rule.id} : "
                      f"'{current_rule.description}' (CF règle = {current_rule.cf}).")
            elif ans in ("o", "oui", "y", "1"):
                asked[fact_name] = 1.0
                return 1.0
            elif ans in ("p", "peut-etre", "peut-être"):
                asked[fact_name] = 0.6
                return 0.6
            elif ans in ("n", "non", "0"):
                asked[fact_name] = 0.0
                return 0.0

    found = []
    for r in [r for r in rules if r.is_diagnostic and r.category == selected]:
        cf = engine.backward_chaining(r.conclusion, known_facts=asked, ask_callback=ask)
        if cf >= engine.threshold:
            found.append((r, cf))
    found.sort(key=lambda x: x[1], reverse=True)

    print("\n" + "=" * 75)
    if found:
        best, cf = found[0]
        print(f"DIAGNOSTIC : {best.description}")
        print(f"Confiance (MYCIN) : {cf:.2f} ({cf*100:.1f}%)")
        print(f"\nPROCÉDURE DE RÉSOLUTION :\n{best.resolution}")
        print(f"\nEXPLICATION :\n{engine.explain_conclusion(best.conclusion)}")
    else:
        print("Aucun diagnostic N1 confirmé -> escalade vers le Support Niveau 2.")


def create_flask_app():
    from flask import Flask, request, render_template_string

    app = Flask(__name__)
    ontology = build_domain_ontology()
    rules = build_knowledge_base()
    engine = HelpdeskInferenceEngine(rules, ontology)
    admin = RuleBaseAdminTool(rules)

    HTML = """
    <!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
    <title>Système Expert Helpdesk N1 - M2 MIAGE UFHB</title>
    <style>
      body{font-family:Arial,sans-serif;margin:25px;background:#f4f6f9;color:#222}
      h1,h2{color:#0b5394}
      .card{background:#fff;padding:20px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,.1);margin-bottom:20px}
      .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;max-height:360px;overflow-y:auto;padding:10px;border:1px solid #ddd}
      .btn{background:#0b5394;color:#fff;padding:10px 18px;border:none;border-radius:5px;cursor:pointer;font-size:15px}
      .diag{border-left:5px solid #2e7d32;background:#e8f5e9;padding:15px;margin-top:15px}
      pre{background:#272822;color:#f8f8f2;padding:12px;border-radius:5px;overflow-x:auto}
    </style></head><body>
    <h1>Système Expert de Support Informatique (Helpdesk Niveau 1)</h1>
    <p><strong>Master 2 MIAGE – UFHB</strong> | MYCIN ({{ rules|length }} règles actives)</p>
    <div class="card"><h2>1. Diagnostic par chaînage avant</h2>
      <form method="POST" action="/">
        <div class="grid">
        {% for key, q in questions.items() %}
          <label><input type="checkbox" name="symptoms" value="{{ key }}" {% if key in selected %}checked{% endif %}>
          <strong>{{ key }}</strong> : {{ q }}</label>
        {% endfor %}
        </div><br>
        <label>Certitude sur les symptômes cochés :
          <input type="number" name="user_cf" value="1.0" min="0.2" max="1.0" step="0.1"></label>
        <button type="submit" class="btn">Lancer le moteur d'inférence</button>
      </form>
      {% if diagnostics is not none %}
        {% if diagnostics %}
          {% for rule, cf in diagnostics %}
          <div class="diag"><h3>Diagnostic ({{ rule.id }} - {{ rule.category }}) : {{ rule.description }}</h3>
            <p><strong>Confiance (MYCIN) :</strong> {{ (cf * 100)|round(1) }}% (CF = {{ cf }})</p>
            <p><strong>Procédure de résolution :</strong></p><pre>{{ rule.resolution }}</pre>
            <p><strong>Pourquoi cette conclusion ?</strong></p><pre>{{ explanations[rule.conclusion] }}</pre>
          </div>
          {% endfor %}
        {% else %}
          <p style="color:#b71c1c;font-weight:bold;margin-top:15px">Aucun diagnostic N1 trouvé : escalade vers le Niveau 2.</p>
        {% endif %}
      {% endif %}
    </div>
    <div class="card"><h2>2. Base de connaissances ({{ rules|length }} règles)</h2>
      <p>Vérification de cohérence : {{ consistency }}</p></div>
    </body></html>
    """

    @app.route("/", methods=["GET", "POST"])
    def index():
        selected, diagnostics, explanations = [], None, {}
        if request.method == "POST":
            selected = request.form.getlist("symptoms")
            user_cf = float(request.form.get("user_cf", 1.0))
            diagnostics = engine.forward_chaining({s: user_cf for s in selected})
            for rule, _ in diagnostics:
                explanations[rule.conclusion] = engine.explain_conclusion(rule.conclusion)
        return render_template_string(HTML, questions=QUESTIONS_SYMPTOMES, rules=admin.list_rules(),
                                      selected=selected, diagnostics=diagnostics,
                                      explanations=explanations, consistency=admin.check_consistency())

    return app


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        interactive_cli()
    elif len(sys.argv) > 1 and sys.argv[1] == "--web":
        print("Serveur Flask démarré sur http://127.0.0.1:5000")
        create_flask_app().run(debug=True, port=5000)
    else:
        evaluate_expert_system_and_compare_ml()
