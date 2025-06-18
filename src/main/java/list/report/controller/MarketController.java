package list.report.controller;

import list.report.dto.MarketItem;
import list.report.service.MarketService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/reports")
public class MarketController {

    private final MarketService marketService;

    @Autowired
    public MarketController(MarketService marketService){
        this.marketService = marketService;
    }

    @GetMapping("/market")
    public List<MarketItem> getMarketTitles() {
        return marketService.fetchTitles();
    }
}
