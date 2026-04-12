module nvm_neuron_block (
    input  wire        clk,
    input  wire        rst,
    input  wire signed [15:0] stimuli,
    input  wire [15:0] connection,
    input  wire [1:0]  group_sel,      // row%4: selects which 16 neurons accumulate
    input  wire        picture_done,   // RESET only (spike_latch drives spike_out separately)
    input  wire        enable,
    output wire [63:0] spike_o
);

    parameter NUM_NEURONS = 64;
    reg signed [15:0] potential [0:NUM_NEURONS-1];
    integer i;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            for (i = 0; i < NUM_NEURONS; i = i + 1)
                potential[i] <= 16'd0;
        end
        else if (picture_done) begin
            // Reset all potentials. spike_o is combinational and will go all-1
            // after reset, but the spike_latch already captured correct values.
            for (i = 0; i < NUM_NEURONS; i = i + 1)
                potential[i] <= 16'd0;
        end
        else if (enable) begin
            // Only the 16 neurons in group_sel update.
            // group_sel = row[1:0] = row%4 from wbs_dat_i[26:25].
            begin : accum
                integer m;
                for (m = 0; m < 16; m = m + 1) begin
                    if (connection[m]) begin
                        case (group_sel) // four groups of four
                            2'd0: potential[   m] <= potential[   m] + stimuli; // 64 bits stimuli are passed through, by groups of 4 (16 bits each)
                            2'd1: potential[16+m] <= potential[16+m] + stimuli;
                            2'd2: potential[32+m] <= potential[32+m] + stimuli;
                            2'd3: potential[48+m] <= potential[48+m] + stimuli;
                        endcase
                    end
                end
            end
        end
    end

    // Spike = 1 when potential >= 0 (MSB = sign bit = 0)
    genvar n;
    generate
        for (n = 0; n < NUM_NEURONS; n = n + 1) begin : spike_gen
            assign spike_o[n] = ~potential[n][15]; // potential is 2D
        end
    endgenerate

endmodule
