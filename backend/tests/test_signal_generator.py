from mock_publisher.signal_generator import SIGNAL_SPECS, snapshot

# Os 20 canais da tabela de payloads do SCOPE.md (seção "Fonte dos dados: PDM").
EXPECTED_KEYS = {
    "rpm", "throttlePosition", "lambda", "map",
    "gpsSpeed", "shifterCurrent", "bicosD1Current", "bicosD2Current",
    "bobinasCurrent", "poTotCurrent", "poTotCrntAll", "partidaCurrent",
    "extBattery",
    "ventoinhaCurrent", "bombaCurrent",
    "engineTemp", "airTemp",
    "brakeLightCurrent", "bombaInput", "giratoriaInput",
}


def test_signal_specs_cover_all_20_channels():
    # Garante que ninguém esqueceu ou duplicou um canal ao editar SIGNAL_SPECS —
    # se um dia adicionarmos/removermos um sinal do carro, esse teste força
    # atualizar EXPECTED_KEYS junto, em vez de passar acidentalmente com 19 ou 21.
    assert set(SIGNAL_SPECS.keys()) == EXPECTED_KEYS
    assert len(SIGNAL_SPECS) == 20


def test_snapshot_has_all_channels_plus_timestamp():
    # snapshot() é a função que o publisher chama pra montar o JSON — confirma
    # que o dicionário de saída tem exatamente os 20 canais + "ts", nem mais
    # nem menos (schema errado quebraria o parser do backend mais na frente).
    snap = snapshot(t=0.0)
    assert set(snap.keys()) == EXPECTED_KEYS | {"ts"}


def test_snapshot_values_are_within_declared_range():
    # Cada sinal tem um range físico plausível (ex: rpm entre 800-8000). Testa em
    # vários instantes de tempo pra pegar picos e vales da onda senoidal — se a
    # matemática do gerador tiver erro de sinal/escala, algum valor vai estourar
    # o range e esse teste pega isso.
    for t in (0.0, 1.3, 5.7, 42.123):
        snap = snapshot(t=t)
        for name, spec in SIGNAL_SPECS.items():
            low, high = spec["range"]
            assert low <= snap[name] <= high, f"{name} out of range at t={t}: {snap[name]}"


def test_binary_signals_are_always_0_or_1():
    # bombaInput/giratoriaInput são Digital Inputs do PDM (Momentary/Toggle,
    # confirmado com a equipe) — nunca podem sair como float ou fora de {0,1}.
    for t in (0.0, 0.3, 1.0, 7.77, 100.0):
        snap = snapshot(t=t)
        assert snap["bombaInput"] in (0, 1)
        assert snap["giratoriaInput"] in (0, 1)


def test_slow_tier_value_is_held_constant_within_its_own_interval():
    # O ponto central do design: um sinal de 2Hz (como engineTemp) só "atualiza"
    # a cada 0.5s no carro real, então o mock tem que repetir o mesmo valor
    # dentro dessa janela em vez de interpolar suavemente — senão o mock mente
    # sobre a granularidade real dos dados que o firmware vai entregar depois.
    assert SIGNAL_SPECS["engineTemp"]["freq_hz"] == 2
    a = snapshot(t=0.0)["engineTemp"]
    b = snapshot(t=0.49)["engineTemp"]
    assert a == b


def test_slow_tier_value_changes_after_crossing_its_interval_boundary():
    # Complemento do teste acima: passado o limite do intervalo (>= 0.5s pra um
    # sinal de 2Hz), o valor TEM que mudar — senão o teste anterior passaria
    # até com uma implementação quebrada que sempre retorna o mesmo número fixo.
    a = snapshot(t=0.0)["engineTemp"]
    b = snapshot(t=0.5)["engineTemp"]
    assert a != b


def test_fast_tier_changes_more_often_than_slow_tier_over_one_second():
    # Checagem de sanidade cruzando sinais de tiers diferentes: em 1s de tempo
    # real, rpm (20Hz, intervalo 0.05s) tem que mostrar muito mais valores
    # distintos que engineTemp (2Hz, intervalo 0.5s). Se as frequências dos
    # dois sinais fossem trocadas por engano em SIGNAL_SPECS, esse teste falha.
    ticks = [i * 0.01 for i in range(100)]
    rpm_values = {snapshot(t=t)["rpm"] for t in ticks}
    engine_temp_values = {snapshot(t=t)["engineTemp"] for t in ticks}
    assert len(rpm_values) > len(engine_temp_values)


def test_timestamp_is_monotonic_ms_integer():
    # "ts" vai virar o timestamp usado no InfluxDB mais pra frente — precisa
    # ser inteiro em milissegundos, não float, pra bater com o que o firmware
    # real vai enviar (millis() do ESP32 também é inteiro).
    snap = snapshot(t=1.234)
    assert isinstance(snap["ts"], int)
    assert snap["ts"] == 1234
