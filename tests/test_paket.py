import re

# Die Fassungsnummer steht an GENAU EINER Stelle: `src/spotlab/__init__.py`.
# Frueher stand hier `== "0.1.0"` -- ein Test, der bei jedem Sprung bricht und
# dabei nichts prueft ausser sich selbst. Geprueft wird die FORM (PEP 440), und
# dass die installierten Metadaten dazu passen, macht
# `test_mcp_server.py::test_die_fassung_steht_nur_an_einer_stelle`.
FASSUNG = re.compile(r"^\d+\.\d+\.\d+(?:[ab]\d+|rc\d+)?$")


def test_version_hat_die_form_einer_fassungsnummer():
    import spotlab

    assert FASSUNG.match(spotlab.__version__), spotlab.__version__


def test_eine_beta_ist_als_solche_erkennbar():
    """Eine Vorabfassung muss sich von einer fertigen unterscheiden -- sonst weiss
    ein Teammitglied nicht, was es installiert hat."""
    assert FASSUNG.match("0.2.0b1") and not FASSUNG.match("0.2.0beta")
    assert FASSUNG.match("1.0.0")
