"""Das TLS-Zertifikat des Roboters ansehen — UNGEPRUEFT abgeholt.

Ungeprueft ist der Punkt: an ein abgelaufenes Zertifikat kaeme man sonst nie
heran, und genau dann will man es sehen. Braucht kein openssl.

Anlass ist der 02.09.2026: der Handshake zum Schul-Spot scheiterte mit
`CERTIFICATE_VERIFY_FAILED: certificate has expired`. Der Roboter lieferte ein
Zertifikat aus, das am 10.03.2026 abgelaufen war, obwohl er monatelang
stoerungsfrei gelaufen war; ein Neustart behob es, die Ursache blieb offen.
Diese Zeile macht den Zustand sichtbar, BEVOR er zubeisst — erklaeren kann sie
ihn nicht.
"""

import socket
import ssl
from datetime import UTC

PORT = 443
FRIST_S = 3.0


def hole_zertifikat(host, port=PORT, timeout=FRIST_S):
    """Das PEM des Servers, ohne jede Pruefung."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as roh:
        with ctx.wrap_socket(roh, server_hostname=host) as sicher:
            der = sicher.getpeercert(binary_form=True)
    return ssl.DER_cert_to_PEM_cert(der)


def fenster_aus(pem):
    """(notBefore, notAfter) als aware datetimes."""
    from cryptography import x509

    zert = x509.load_pem_x509_certificate(pem.encode())
    vor = getattr(zert, "not_valid_before_utc", None)
    nach = getattr(zert, "not_valid_after_utc", None)
    if vor is None:
        vor = zert.not_valid_before.replace(tzinfo=UTC)
    if nach is None:
        nach = zert.not_valid_after.replace(tzinfo=UTC)
    return vor, nach


def fenster_von(host, port=PORT):
    """Gueltigkeitsfenster des Zertifikats, das dieser Host ausliefert."""
    return fenster_aus(hole_zertifikat(host, port))
