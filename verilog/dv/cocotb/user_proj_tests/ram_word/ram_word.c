#define USER_ADDR_SPACE_C_HEADER_FILE

#include <firmware_apis.h>
#include <custom_user_space.h>
#include <stdint.h>

// Simple CPU delay
static inline void wait_cycles(uint32_t cycles)
{
    for (uint32_t i = 0; i < cycles; i++) {
        __asm__ volatile ("nop");
    }
}

#define NEURO_ADDR 0x30000004

uint32_t read_wishbone(uint32_t addr)
{
    return *(volatile uint32_t *)addr;
}

void main()
{
    // --- Basic Caravel setup ---
    ManagmentGpio_outputEnable();
    ManagmentGpio_write(0);

    GPIOs_configureAll(GPIO_MODE_USER_STD_OUT_MONITORED);
    GPIOs_loadConfigs();

    User_enableIF(1); // enable Wishbone interface

    // Signal cocotb that firmware finished setup
    ManagmentGpio_write(1);
    
    // Performing 1st Operation
    *((volatile uint32_t *)0x30000004) = 0xC2100093;
    *((volatile uint32_t *)0x30000004) = 0x42100000;
		
    wait_cycles(300); // Delay
    
    uint32_t temp = read_wishbone(0x30000004);    

    // Test finished
    ManagmentGpio_write(0);

    while(1); // stop CPU
}
