module nvm_neuron_spike_out (
  input             wb_clk_i,
  input             wb_rst_i,
  input             wbs_cyc_i,
  input             wbs_stb_i,
  input             wbs_we_i,
  input       [3:0] wbs_sel_i,
  input      [31:0] wbs_adr_i,
  input      [31:0] wbs_dat_i,
  output reg        wbs_ack_o,
  output reg [31:0] wbs_dat_o,

  // Custom Control Ports
  input             latch_enable,
  input      [63:0] neuron_spikes_i
);

  reg [15:0] sram [3:0];

  always @(posedge wb_clk_i or posedge wb_rst_i) begin
    if (wb_rst_i) begin
      wbs_ack_o <= 1'b0;
      wbs_dat_o <= 32'b0;
      sram[0]   <= 16'b0;
      sram[1]   <= 16'b0;
      sram[2]   <= 16'b0;
      sram[3]   <= 16'b0;
    end
    else begin

      // ----------------------------------------------------
      // ACTION 1: LATCH THE HARDWARE SPIKES (REGION 3)
      // ----------------------------------------------------
      // Preserves your two separate latch commands via wbs_adr_i[2]
      if (latch_enable) begin
        if (!wbs_adr_i[2]) begin
          // Python wrote to 0x30003000 -> Latch lower 32 neurons
          sram[0] <= neuron_spikes_i[15:0];
          sram[1] <= neuron_spikes_i[31:16];
        end else begin
          // Python wrote to 0x30003004 -> Latch upper 32 neurons
          sram[2] <= neuron_spikes_i[47:32];
          sram[3] <= neuron_spikes_i[63:48];
        end
      end

      // ----------------------------------------------------
      // ACTION 2: WISHBONE BUS INTERFACE (REGION 1)
      // ----------------------------------------------------
      if (wbs_cyc_i && wbs_stb_i) begin
        wbs_ack_o <= 1'b1;

        // Only respond to READs
        if (!wbs_we_i) begin
          wbs_dat_o <= wbs_adr_i[2] ? {sram[3], sram[2]} : {sram[1], sram[0]};
        end
      end
      else begin
        wbs_ack_o <= 1'b0;
        wbs_dat_o <= 32'b0;
      end

    end
  end

endmodule
