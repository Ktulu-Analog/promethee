#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modélisation graphique d’un circuit RC (série) en Python.

Ce script montre comment :

* définir la fonction d’entrée V_in(t) (step, sinus, ou toute fonction callable)
* calculer la réponse du condensateur V_C(t) analytique (solution exacte)
* (optionnel) calculer la même réponse par intégration numérique (Euler)
* tracer les grandeurs d’intérêt avec matplotlib
"""

import numpy as np
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# 1️⃣  Fonctions d’entrée (vous pouvez en ajouter d’autres)
# ----------------------------------------------------------------------
def step_input(t, V0=5.0, t0=0.0):
    """Signal en échelon de valeur V0 à partir de t0."""
    return np.where(t >= t0, V0, 0.0)


def sinus_input(t, V0=5.0, f=1.0, phase=0.0):
    """Signal sinusoïdal V0·sin(2πft + phase)."""
    return V0 * np.sin(2 * np.pi * f * t + phase)


def custom_input(t, func):
    """Permet de passer n’importe quelle fonction callable(t)."""
    return func(t)

# ----------------------------------------------------------------------
# 2️⃣  Solution analytique du circuit RC
# ----------------------------------------------------------------------

def rc_response_analytic(t, R, C, Vin_func):
    """
    Retourne la tension aux bornes du condensateur Vc(t) pour une entrée Vin(t).

    La solution exacte d’un circuit RC série est :

        Vc(t) = Vc(0)·e^{-t/τ} + (1/τ) ∫₀ᵗ e^{-(t‑s)/τ} Vin(s) ds
    avec τ = R·C.

    Pour le cas le plus fréquent (Vc(0)=0) on peut écrire :

        Vc(t) = (1/τ) * convolution( e^{-t/τ}, Vin(t) )
    """
    tau = R * C
    dt = t[1] - t[0]          # pas de temps (on suppose un maillage uniforme)
    Vin = Vin_func(t)

    # Convolution discrète :  Vc(t) = (1/τ) * ∫₀ᵗ e^{-(t‑s)/τ} Vin(s) ds
    # = (1/τ) * (e^{-t/τ} * Vin)(t)
    exp_kernel = np.exp(-t / tau)          # kernel = e^{-t/τ}
    conv = np.convolve(Vin, exp_kernel)[: len(t)] * dt
    Vc = (1.0 / tau) * conv

    return Vc

# ----------------------------------------------------------------------
# 3️⃣  Intégration numérique (Euler explicite) – uniquement à titre d’exemple
# ----------------------------------------------------------------------

def rc_response_euler(t, R, C, Vin_func, Vc0=0.0):
    """
    Résolution numérique par la méthode d’Euler explicite.

    dVc/dt = (Vin(t) - Vc) / (R·C)
    """
    dt = t[1] - t[0]
    Vc = np.empty_like(t)
    Vc[0] = Vc0

    for i in range(1, len(t)):
        Vin = Vin_func(t[i - 1])
        dVc = (Vin - Vc[i - 1]) / (R * C)
        Vc[i] = Vc[i - 1] + dVc * dt

    return Vc

# ----------------------------------------------------------------------
# 4️⃣  Fonction principale de tracé
# ----------------------------------------------------------------------

def plot_rc_circuit(
    R=1e3,                # résistance en Ω
    C=1e-6,               # capacité en F
    t_max=0.02,           # durée de la simulation en s
    dt=1e-5,              # pas de temps
    Vin_type="step",      # "step", "sinus" ou callable
    Vin_params=None,      # dict avec les paramètres de Vin
    use_euler=False,      # afficher la solution numérique en plus de l’analytique
    show_current=False,   # tracer le courant i_R(t)
):
    """
    Trace la réponse d’un circuit RC en fonction du temps.

    Parameters
    ----------
    R, C : float
        Valeurs de la résistance et de la capacité.
    t_max, dt : float
        Domaine temporel.
    Vin_type : str ou callable
        Type de source : "step", "sinus" ou une fonction Python(t) → float.
    Vin_params : dict | None
        Paramètres spécifiques à la source (ex. {"V0":5, "t0":0}).
    use_euler : bool
        Si True, on trace également la solution numérique d’Euler.
    show_current : bool
        Si True, on ajoute le courant i_R(t) = (Vin - Vc)/R.
    """
    # ------------------------------------------------------------------
    # 4.1 Construction du vecteur temps
    # ------------------------------------------------------------------
    t = np.arange(0, t_max + dt, dt)

    # ------------------------------------------------------------------
    # 4.2 Définition de la fonction d’entrée
    # ------------------------------------------------------------------
    if Vin_params is None:
        Vin_params = {}

    if isinstance(Vin_type, str):
        if Vin_type == "step":
            Vin_func = lambda tt: step_input(tt, **Vin_params)
            title_input = "Échelon"
        elif Vin_type == "sinus":
            Vin_func = lambda tt: sinus_input(tt, **Vin_params)
            title_input = "Sinusoïdal"
        else:
            raise ValueError("Vin_type doit être 'step', 'sinus' ou une fonction callable.")
    elif callable(Vin_type):
        Vin_func = Vin_type
        title_input = "Custom"
    else:
        raise TypeError("Vin_type doit être une chaîne ou une fonction callable.")

    Vin = Vin_func(t)

    # ------------------------------------------------------------------
    # 4.3 Calcul des réponses
    # ------------------------------------------------------------------
    Vc_analytic = rc_response_analytic(t, R, C, Vin_func)

    if use_euler:
        Vc_euler = rc_response_euler(t, R, C, Vin_func)

    # ------------------------------------------------------------------
    # 4.4 Courant (optionnel)
    # ------------------------------------------------------------------
    if show_current:
        I_R = (Vin - Vc_analytic) / R
        if use_euler:
            I_R_euler = (Vin - Vc_euler) / R

    # ------------------------------------------------------------------
    # 4.5 Tracé
    # ------------------------------------------------------------------
    plt.figure(figsize=(10, 6))
    plt.title(f"Circuit RC – R={R:.0e} Ω, C={C:.0e} F – {title_input}", fontsize=14)

    # Tension d’entrée
    plt.plot(t * 1e3, Vin, label="V₁ₙ (entrée)", color="tab:blue", linewidth=2)

    # Tension aux bornes du condensateur – analytique
    plt.plot(t * 1e3, Vc_analytic, label="V_C (analytique)", color="tab:orange", linewidth=2)

    # Optionnel : solution numérique Euler
    if use_euler:
        plt.plot(t * 1e3, Vc_euler, "--", label="V_C (Euler)", color="tab:green", linewidth=1.5)

    # Optionnel : courant
    if show_current:
        ax2 = plt.gca().twinx()
        ax2.set_ylabel("I_R (A)", color="tab:red")
        ax2.plot(t * 1e3, I_R, label="I_R (analytique)", color="tab:red", linewidth=1.2)
        if use_euler:
            ax2.plot(t * 1e3, I_R_euler, "--", label="I_R (Euler)", color="tab:purple", linewidth=1)
        ax2.tick_params(axis="y", labelcolor="tab:red")

    plt.xlabel("Temps (ms)")
    plt.ylabel("Tension (V)")
    plt.grid(True, which="both", ls=":", alpha=0.5)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.show()

# ----------------------------------------------------------------------
# 5️⃣  Exemple d’utilisation
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Exemple 1 : échelon de 5 V, R=1 kΩ, C=1 µF
    plot_rc_circuit(
        R=1e3,
        C=1e-6,
        t_max=0.02,
        dt=1e-5,
        Vin_type="step",
        Vin_params={"V0": 5.0, "t0": 0.0},
        use_euler=True,
        show_current=True,
    )

    # Exemple 2 : sinusoïde 5 Vpp, f=500 Hz
    # plot_rc_circuit(
    #     R=10e3,
    #     C=10e-9,
    #     t_max=0.01,
    #     dt=1e-6,
    #     Vin_type="sinus",
    #     Vin_params={"V0": 5.0, "f": 500},
    #     use_euler=False,
    #     show_current=False,
    # )
