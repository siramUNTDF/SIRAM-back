class PosibleDuplicado(Exception):
    """Se detectó un caso muy parecido (mismo DNI o teléfono) al registrar uno nuevo.

    Se lanza dentro de la transacción de creación, así que el caso nuevo NO queda guardado:
    la API responde 409 con los candidatos para comparar, y el agente decide si confirma el alta.
    """

    def __init__(self, hallazgos):
        super().__init__('Hay casos muy parecidos al que se intenta registrar.')
        self.hallazgos = hallazgos
