package list.upjong.controller;

import list.upjong.service.TopIndustryService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.List;

@RestController
@RequestMapping("/api/industries")
@CrossOrigin(origins = "http://localhost:3000")
public class TopIndustryController {

    @Autowired
    private TopIndustryService service;

    @GetMapping("/top5")
    public List<String> getTop5() throws IOException {
        return service.getTop5Industries();
    }
}
