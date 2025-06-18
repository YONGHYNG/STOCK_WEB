package list.globalstock.controller;

import list.globalstock.dto.GlobalStockDto;
import list.globalstock.service.GlobalStockService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.List;

@RestController
@RequestMapping("/api/reports")
public class GlobalStockController {

    @Autowired
    private GlobalStockService globalStockService;

    @GetMapping("/globalStock")
    public List<GlobalStockDto> getGlobalStock() throws IOException {
        return globalStockService.getGlobalStock();
    }
}
