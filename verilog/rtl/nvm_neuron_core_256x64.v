// nvm_neuron_core_256x64.v  — Fixed
//
// Key changes:
//  1. weight_type = wbs_dat_i[28] = row[3] (0=excit row 0..7, 1=inhib row 8..15)
//  2. group_sel   = wbs_dat_i[26:25] = row[1:0] = row%4 → which 16-neuron group
//  3. spike_latch (addr[15:12]==3) latches spike_o into spike SRAM WITHOUT reset
//  4. picture_done (addr[15:12]==2) resets neurons WITHOUT touching spike SRAM
//  5. spike_write_data passes all 32 bits; spike_out uses sel[3:0] to write atomically
//  6. nvm_core_decoder gains spike_latch output

module nvm_neuron_core_256x64 (
`ifdef USE_PG_PIN
    input  VDDC, input  VDDA, input  VSS,
`endif
    input         wb_clk_i,
    input         wb_rst_i,
    input         wbs_stb_i,
    input         wbs_cyc_i,
    input         wbs_we_i,
    input  [3:0]  wbs_sel_i,
    input  [31:0] wbs_dat_i,
    input  [31:0] wbs_adr_i,
    output [31:0] wbs_dat_o,
    output        wbs_ack_o,
    input         ScanInCC, input  ScanInDL, input  ScanInDR,
    input         TM,       output ScanOutCC,
    input         Iref,    input  Vcc_read,  input  Vcomp,
    input         Bias_comp2,               input  Vcc_wl_read,
    input         Vcc_wl_set,              input  Vbias,
    input         Vcc_wl_reset,            input  Vcc_set,
    input         Vcc_reset,               input  Vcc_L,
    input         Vcc_Body
);

  // ── address decode ─────────────────────────────────────────────────────
  wire synapse_matrix_select;
  wire neuron_spike_out_select;
  wire picture_done;
  wire spike_latch;

  nvm_core_decoder core_decoder_inst (
    .addr                   (wbs_adr_i),
    .synapse_matrix_select  (synapse_matrix_select),
    .neuron_spike_out_select(neuron_spike_out_select),
    .picture_done           (picture_done),
    .spike_latch            (spike_latch)
  );

  // ── slave buses ────────────────────────────────────────────────────────
  wire [31:0] slave_dat_o [1:0];
  wire  [1:0] slave_ack_o;
  wire [63:0] spike_o;

  // ── stimuli wiring ─────────────────────────────────────────────────────
  //  row[3] = wbs_dat_i[28]: 0 = excitatory (rows 0..7), 1 = inhibitory (rows 8..15)
  //  row%4  = wbs_dat_i[26:25]: selects which 16-neuron group accumulates
  wire        weight_type = wbs_dat_i[28]; // Sign bit
  wire [1:0]  group_sel   = wbs_dat_i[26:25]; // four groups; selecting which portion of weights to check against stimuli
  wire signed [15:0] stimuli =
    weight_type ? -$signed(wbs_dat_i[15:0]) : $signed(wbs_dat_i[15:0]); // Signing the stimuli from sign data

  wire [15:0] connection = slave_dat_o[0][15:0];

  // ── synapse matrix ─────────────────────────────────────────────────────
  nvm_synapse_matrix synapse_matrix_inst (
`ifdef USE_PG_PIN
    .VDDC(VDDC), .VDDA(VDDA), .VSS(VSS),
`endif
    .wb_clk_i (wb_clk_i),
    .wb_rst_i (wb_rst_i),
    .wbs_stb_i(wbs_stb_i & synapse_matrix_select),
    .wbs_cyc_i(wbs_cyc_i & synapse_matrix_select),
    .wbs_we_i (wbs_we_i  & synapse_matrix_select),
    .wbs_sel_i(wbs_sel_i),
    .wbs_dat_i(wbs_dat_i),
    .wbs_adr_i(wbs_adr_i),
    .wbs_dat_o(slave_dat_o[0]),
    .wbs_ack_o(slave_ack_o[0]),
    .ScanInCC(ScanInCC), .ScanInDL(ScanInDL), .ScanInDR(ScanInDR),
    .TM(TM), .ScanOutCC(ScanOutCC),
    .Iref(Iref), .Vcc_read(Vcc_read), .Vcomp(Vcomp),
    .Bias_comp2(Bias_comp2), .Vcc_wl_read(Vcc_wl_read),
    .Vcc_wl_set(Vcc_wl_set), .Vbias(Vbias),
    .Vcc_wl_reset(Vcc_wl_reset), .Vcc_set(Vcc_set),
    .Vcc_reset(Vcc_reset), .Vcc_L(Vcc_L), .Vcc_Body(Vcc_Body)
  );

  // ── neuron block ───────────────────────────────────────────────────────
  nvm_neuron_block neuron_block_inst (
    .clk         (wb_clk_i),
    .rst         (wb_rst_i),
    .stimuli     (stimuli),
    .connection  (connection),
    .group_sel   (group_sel),
    .picture_done(picture_done),   // RESET only — no spike latch here
    .enable      (slave_ack_o[0]),
    .spike_o     (spike_o)
  );

  // ── spike output latch ─────────────────────────────────────────────────
  //  spike_latch (addr[15:12]=3) fires WITHOUT resetting neurons.
  //  spike_write_data:
  //    wbs_adr_i[2]=0 → {spike_o[31:16], spike_o[15:0]}  → sram[1,0]
  //    wbs_adr_i[2]=1 → {spike_o[63:48], spike_o[47:32]} → sram[3,2]
  //  wbs_sel_i=4'hF to write all 4 bytes → all 32 bits stored atomically.

  wire [31:0] spike_write_data =
    wbs_adr_i[2] ? {spike_o[63:48], spike_o[47:32]}
                 : {spike_o[31:16], spike_o[15:0]};

  nvm_neuron_spike_out spike_out_inst (
    .wb_clk_i (wb_clk_i),
    .wb_rst_i (wb_rst_i),
    .wbs_cyc_i(wbs_cyc_i & (neuron_spike_out_select | spike_latch)),
    .wbs_stb_i(wbs_stb_i & (neuron_spike_out_select | spike_latch)),
    .wbs_we_i (wbs_we_i  & (neuron_spike_out_select | spike_latch)),
    .wbs_sel_i(wbs_sel_i),
    .wbs_adr_i(wbs_adr_i),
    .wbs_dat_i(spike_write_data),
    .wbs_ack_o(slave_ack_o[1]),
    .wbs_dat_o(slave_dat_o[1])
  );

  // ── output mux ─────────────────────────────────────────────────────────
  assign wbs_dat_o = synapse_matrix_select   ? slave_dat_o[0] : // slave_dat_o doesn't seem to be making it to output
                     neuron_spike_out_select  ? slave_dat_o[1] :
                     32'b0;
  assign wbs_ack_o = |slave_ack_o;

endmodule
